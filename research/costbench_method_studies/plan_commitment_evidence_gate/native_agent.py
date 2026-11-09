"""Symbolic policy adapter for unmodified official CostBench run_single_query.

Only archived pre-event DeepSeek responses are replayed; thereafter the policy
selects native tool calls and final answers using current model-visible tool
definitions and actual native state. No provider requests or oracle fields.
"""
import copy
import html
import hashlib
import json
import re
import time
from types import SimpleNamespace

from core import decide, shortest, local_repair, parse_public_tools, simulate, price
from plan_memory import recover_pre_event_commitment
from replay_gate import ReplayCompletions, ReachedCheckpoint, AttrDict, canonical

POLICIES=("AB_GATE",)
PENALTY=0.25
ID=re.compile(r"<([A-Za-z][A-Za-z0-9_]*[0-9]{5})>")
BARE=re.compile(r"\b([A-Za-z][A-Za-z0-9_]*[0-9]{5})\b")
ERROR=("[ERROR]","Tool execution failed","Error:")

def calls(message):
    result=[]
    for tool in (message.get("tool_calls") or []):
        if isinstance(tool,dict):
            fn=tool.get("function") or {}
            result.append((tool.get("id"),fn.get("name") or tool.get("name"),
                           fn.get("arguments") or tool.get("arguments")))
        else:
            result.append((tool.id,tool.function.name,tool.function.arguments))
    return result

def normalize_public_identifier(value):
    """Canonicalize only already visible IDs; never fabricate a missing value."""
    if not isinstance(value,str):return value
    decoded=html.unescape(value)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*[0-9]{5}",decoded):
        return "<"+decoded+">"
    if re.fullmatch(r"<[A-Za-z][A-Za-z0-9_]*[0-9]{5}>",decoded):
        return decoded
    return value

def observed_id(value):
    if not isinstance(value,str):return None
    value=html.unescape(value)
    found=ID.findall(value)
    if found:return "<"+found[-1]+">"
    found=BARE.findall(value)
    return found[-1] if found else None

def type_inventory(messages,old_specs,new_specs):
    typed={}
    call_index={}
    for msg in messages:
        role=msg.get("role")
        if role=="user":
            for candidate in ID.findall(html.unescape(msg.get("content") or "")):
                m=re.search(r"[0-9]{5}$",candidate)
                if m:typed.setdefault(candidate[:m.start()],"<"+candidate+">")
        elif role=="assistant":
            for call_id,name,arg in calls(msg):
                call_index[call_id]=name
                try: values=json.loads(arg)
                except (ValueError,TypeError): continue
                if isinstance(values,dict):
                    for field,value in values.items():
                        if isinstance(value,str) and value:typed[field]=normalize_public_identifier(value)
        elif role=="tool":
            raw=msg.get("content") or ""
            if raw.startswith(ERROR):continue
            name=call_index.get(msg.get("tool_call_id"))
            spec=new_specs.get(name) or old_specs.get(name)
            if spec:
                value=observed_id(raw)
                if value:typed[spec.output]=normalize_public_identifier(value)
    return typed

class SymbolicContinuation(ReplayCompletions):
    def __init__(self,archive,mode,goal,state_supplier,penalty=PENALTY,max_steps=7):
        step=(archive.get("block_stats") or {}).get("block_step",[None])[0]
        if not isinstance(step,int):raise ValueError("no observed change event")
        super().__init__(archive,step)
        self.mode=mode;self.goal=goal;self.state_supplier=state_supplier
        self.penalty=penalty;self.max_steps=max_steps
        self.first_interface=None;self.old=None;self.new=None
        self.state=None;self.conversation_digest=None
        self.plan=None;self.decision=None;self.selected=None
        self.plan_commitment=None;self.evidence_gate=None
        self.started=False;self.finished=False;self.generated=[];self.errors=[]
        self.planning_seconds=None;self.search_expansions=None;self.checkpoint_tools_digest=None

    async def create(self,*,messages,tools,**kwargs):
        if self.first_interface is None:self.first_interface=copy.deepcopy(tools)
        if self.step<self.trigger_step:
            return await super().create(messages=messages,tools=tools,**kwargs)
        if not self.started:
            try:await super().create(messages=messages,tools=tools,**kwargs)
            except ReachedCheckpoint:pass
            self.started=True
            self.state=frozenset(self.state_supplier())
            self.checkpoint_tools_digest=self.fork_public_tools_sha256
            normalized=[]
            for m in messages:
                normalized.append({"role":m.get("role"),"content":m.get("content"),
                    "calls":calls(m),"tool_call_id":m.get("tool_call_id")})
            self.conversation_digest=hashlib.sha256(
                canonical(normalized).encode()).hexdigest()
            self.old=parse_public_tools(self.first_interface)
            self.new=parse_public_tools(tools)
            if self.goal in self.state:
                self.plan=();self.selected="ALREADY_GOAL"
            else:
                remaining=self.max_steps-self.trigger_step-1
                if remaining<=0:raise ValueError("no steps available after native prefix")
                start=time.perf_counter()
                goal_types=frozenset({self.goal})
                if self.mode=="SCSR":
                    self.decision=decide(self.state,self.goal,self.first_interface,tools,
                                         switch_penalty=self.penalty,max_tools=remaining)
                    self.plan=self.decision.suffix
                    self.selected=self.decision.kind
                    d=self.decision
                    self.search_expansions=(d.old_search_expansions+
                                            d.new_search_expansions+d.local_search_expansions)
                elif self.mode=="AB_GATE":
                    # A: only the actual pre-event native assistant plan text,
                    # NOT a shortest path reconstructed to look like a commitment.
                    original_assistants=self.expected
                    prefix_names=[]
                    for turn in original_assistants[:self.trigger_step]:
                        for _,name,_ in calls(turn):prefix_names.append(name)
                    if not original_assistants or len(prefix_names)!=self.trigger_step:
                        raise AssertionError("archived pre-event plan source missing")
                    committed=recover_pre_event_commitment(
                        original_assistants[0].get("content") or "",
                        self.old,prefix_names,self.state,goal_types)
                    self.plan_commitment={
                        "status":committed.status,
                        "full_path":list(committed.full_path),
                        "remaining_suffix":list(committed.remaining_path),
                        "matching_candidates":committed.matching_candidates,
                        "source":committed.provenance,
                        "verbatim_evidence_excerpt":committed.evidence}
                    # B: exact public evidence check. Price changes are
                    # observable; requesting extra LLM verification for them
                    # cannot reveal new tool-price evidence.
                    newbest=shortest(self.state,goal_types,self.new,remaining)
                    if newbest is None:raise ValueError("no feasible current public suffix")
                    if committed.status=="VALID_PRE_EVENT_COMMITMENT":
                        candidate=committed.remaining_path
                        updated=price(candidate,self.new)
                        margin=updated-newbest.cost
                        if margin<=self.penalty+0.0000001:
                            self.plan=candidate
                            self.selected="RETAIN_OBSERVED_LLM_PLAN"
                            cause="observed_plan_remains_feasible_within_margin"
                        else:
                            self.plan=newbest.names
                            self.selected="SWITCH_FROM_OBSERVED_LLM_PLAN"
                            cause="verified_public_cost_gap_exceeds_margin"
                    else:
                        self.plan=newbest.names
                        self.selected="NO_VERIFIABLE_PLAN_FULL_GRAPH_FALLBACK"
                        cause="no_machine_checkable_pre_event_text_commitment"
                    self.evidence_gate={
                        "decision":self.selected,
                        "reason":cause,
                        "current_graph_exact_search":True,
                        "new_llm_verification_calls":0,
                        "old_plan_genuinely_model_written":committed.status=="VALID_PRE_EVENT_COMMITMENT",
                        "old_plan_updated_cost":price(committed.remaining_path,self.new)
                            if committed.status=="VALID_PRE_EVENT_COMMITMENT" else None,
                        "verified_public_cheapest_cost":newbest.cost,
                        "tool_graph_search_expansions":newbest.expansions,
                        "switch_margin_assumed_tool_units":self.penalty}
                    self.search_expansions=newbest.expansions
                    self.decision=SimpleNamespace(
                        kind=self.selected,suffix=self.plan,
                        incumbent=committed.remaining_path
                            if committed.status=="VALID_PRE_EVENT_COMMITMENT" else (),
                        new_optimal=newbest.names,old_cost=None,
                        incumbent_post_cost=self.evidence_gate["old_plan_updated_cost"],
                        selected_post_cost=price(self.plan,self.new),
                        full_post_cost=newbest.cost,upper_bound_gain=None,
                        switch_penalty=self.penalty,
                        certificate="checked_actual_LLM_text_and_public_graph",
                        old_search_expansions=0,
                        new_search_expansions=newbest.expansions,
                        local_search_expansions=0,
                        planning_wall_seconds=0.0)
                elif self.mode=="FULL_REPLAN":
                    plan=shortest(self.state,goal_types,self.new,remaining)
                    if plan is None:raise ValueError("no feasible current full path")
                    self.plan=plan.names;self.selected="FULL_REPLAN"
                    self.search_expansions=plan.expansions
                else:
                    incumbent=shortest(self.state,goal_types,self.old,remaining)
                    if incumbent is None:raise ValueError("no valid old-cost incumbent")
                    self.search_expansions=incumbent.expansions
                    if self.mode=="RETAIN":
                        self.plan=incumbent.names;self.selected="RETAIN"
                    elif self.mode=="LOCAL_REPAIR":
                        repaired=local_repair(self.state,goal_types,incumbent.names,
                                              self.new,remaining)
                        if repaired:
                            self.search_expansions+=repaired.expansions
                            self.plan=repaired.names;self.selected="LOCAL_REPAIR"
                        elif (actual:=simulate(self.state,incumbent.names,self.new)) is not None and goal_types<=actual:
                            self.plan=incumbent.names;self.selected="LOCAL_REPAIR_RETAIN_FALLBACK"
                        else:
                            full=shortest(self.state,goal_types,self.new,remaining)
                            if full is None:raise ValueError("local repair and full recovery both infeasible")
                            self.search_expansions+=full.expansions
                            self.plan=full.names;self.selected="LOCAL_REPAIR_FULL_FALLBACK"
                    else:raise ValueError("unknown controller mode")
                self.planning_seconds=round(time.perf_counter()-start,7)
                end=simulate(self.state,self.plan,self.new)
                if end is None or self.goal not in end:
                    raise AssertionError("selected path fails public dependency check")
        history_tools=[m for m in messages if m.get("role")=="tool"]
        if len(history_tools)!=self.trigger_step+len(self.generated):
            raise AssertionError("native tool step differs from controller plan")
        for item in history_tools[self.trigger_step:]:
            if (item.get("content") or "").startswith(ERROR):
                self.errors.append("NATIVE_TOOL_FAILURE")
                raise ValueError("observed tool error; stop without inventing data")
        known=type_inventory(messages,self.old,self.new)
        if len(self.generated)<len(self.plan):
            name=self.plan[len(self.generated)]
            spec=self.new[name]
            missing=sorted(t for t in spec.inputs if t not in known)
            if missing:
                self.errors.append("UNOBSERVED_ARGUMENT_TYPES:"+",".join(missing))
                raise ValueError("cannot synthesize arguments with missing observed data")
            arguments=json.dumps({key:known[key] for key in sorted(spec.inputs)},
                                 sort_keys=True,ensure_ascii=False)
            i=len(self.generated)
            call_id="call_"+hashlib.sha256(
                f"{self.mode}:{i}:{name}".encode()).hexdigest()[:24]
            self.generated.append({"id":call_id,"name":name,"arguments":arguments})
            call=AttrDict(id=call_id,type="function",
                          function=AttrDict(name=name,arguments=arguments))
            msg=SimpleNamespace(content="Executing verified dependency path.",
                                tool_calls=[call])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        if self.goal not in set(self.state_supplier()):
            raise AssertionError("native state lacks goal after planned suffix")
        candidate=known.get(self.goal)
        if not candidate:
            self.errors.append("FINAL_ID_UNOBSERVED")
            raise ValueError("cannot infer exact answer ID from native observation")
        self.finished=True
        msg=SimpleNamespace(content="<answer> "+candidate+" </answer>",tool_calls=[])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
