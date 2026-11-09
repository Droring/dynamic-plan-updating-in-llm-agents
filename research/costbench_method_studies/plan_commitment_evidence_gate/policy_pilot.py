#!/usr/bin/env python3
"""Same-checkpoint prompt-policy PILOT using the pinned official CostBench Agent loop.

The only intervention is a user-visible control instruction after a replayed
native cost-change event; all subsequent native tool simulation and state
updates remain in official env.run.run_single_query. This is NOT a benchmark of
formal RETAIN/LOCAL_REPAIR algorithms without an LLM-committed suffix.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from replay_gate import (BASE,ReachedCheckpoint,ReplayCompletions,OfflineClient,
                         load_dev80,load_dynamic,native_args,canonical)

POLICIES=("native_continue","verify_prompt","local_focus_prompt",
          "full_reconsider_prompt","adaptive_prompt")
PROMPTS={
 "native_continue":None,
 "verify_prompt":(
   "The tool environment has changed. Before the next tool call, verify the current "
   "visible tool costs against your intended continuation. Compare concrete feasible "
   "alternatives using the same obtained data types; change course only when justified. "
   "Do not assume a lower cost without a numeric comparison."),
 "local_focus_prompt":(
   "The tool environment has changed. Inspect the next executable tool and its "
   "prerequisites. Prefer to keep already valid intermediate results and make the "
   "smallest feasible adjustment to the remaining tool sequence. Do not restart "
   "completed work. If no valid local continuation exists, reconsider globally."),
 "full_reconsider_prompt":(
   "The tool environment has changed. Discard cost estimates for unexecuted actions "
   "from the prior situation. From the actual obtained data-type state and the tools "
   "currently visible, reconsider the entire remaining execution path and choose a "
   "feasible lowest-cost continuation. Do not repeat successful prior actions.")
}
COST_RE=re.compile(r"This tool has a cost of ([0-9]+(?:\.[0-9]+)?) units\.")

def public_costs(tools):
    costs={}
    for item in tools or []:
        function=item.get("function") or {}
        match=COST_RE.search(function.get("description") or "")
        if match:
            costs[function["name"]]=float(match.group(1))
    return costs

def choose_adaptive(before,after):
    old=public_costs(before);new=public_costs(after)
    common=sorted(set(old)&set(new))
    if not common or len(common)<max(2,len(new)//2):
        return "verify_prompt",{"reason":"incomplete_public_cost_fields","common":len(common)}
    changes=[abs(new[name]-old[name])/max(old[name],.01) for name in common]
    mean=sum(changes)/len(changes)
    if mean<.05:action="native_continue"
    elif mean<.18:action="verify_prompt"
    elif mean<.35:action="local_focus_prompt"
    else:action="full_reconsider_prompt"
    return action,{"reason":"mean_relative_public_tool_cost_change",
                   "mean_relative_change":round(mean,6),
                   "common_tools":len(common),"total_current_tools":len(new)}

def scrub_message(msg):
    value={"role":msg.get("role"),"content":msg.get("content")}
    calls=msg.get("tool_calls") or []
    if calls:
        value["tool_calls"]=[{
            "id":c.get("id") if isinstance(c,dict) else getattr(c,"id",None),
            "name":(c.get("function") or {}).get("name") if isinstance(c,dict)
                   else c.function.name,
            "arguments":(c.get("function") or {}).get("arguments") if isinstance(c,dict)
                         else c.function.arguments,
        } for c in calls]
    if msg.get("tool_call_id"):value["tool_call_id"]=msg["tool_call_id"]
    return value

class ForkedCompletions(ReplayCompletions):
    def __init__(self,archive,step,policy,upstream_client,expected_tools_digest,
                 shared_snapshot,cap=4):
        super().__init__(archive,step)
        self.policy=policy
        self.live=upstream_client
        self.expected_tools_digest=expected_tools_digest
        self.state_supplier=shared_snapshot
        self.cap=cap
        self.entered=False
        self.real_calls=0
        self.usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
        self.usage_available=True
        self.failure_types=[]
        self.provider_failure_status_codes=[]
        self.provider_failure_codes=[]
        self.provider_safe_error_hints=[]
        self.policy_effective=None
        self.choice_metrics={}
        self.fork_conversation_digest=None
        self.fork_native_state_digest=None
        self.elapsed_seconds=0.0
        self.initial_public_tools=None

    async def create(self,*,messages,tools,**kwargs):
        if self.step<self.trigger_step:
            if self.initial_public_tools is None:self.initial_public_tools=copy.deepcopy(tools)
            return await super().create(messages=messages,tools=tools,**kwargs)
        if not self.entered:
            try:
                await super().create(messages=messages,tools=tools,**kwargs)
            except ReachedCheckpoint:
                pass
            if self.fork_public_tools_sha256!=self.expected_tools_digest:
                raise AssertionError("public tool snapshot differs from sealed native replay gate")
            state=self.state_supplier()
            self.fork_native_state_digest=hashlib.sha256(canonical(sorted(state)).encode()).hexdigest()
            self.fork_conversation_digest=hashlib.sha256(
                canonical([scrub_message(x) for x in messages]).encode()).hexdigest()
            if self.policy=="adaptive_prompt":
                choice,metrics=choose_adaptive(self.initial_public_tools,tools)
                self.policy_effective=choice
                self.choice_metrics=metrics
            else:
                self.policy_effective=self.policy
            instruction=PROMPTS[self.policy_effective]
            if instruction is not None:
                # Edit only the intervention message. Prior history and native tools
                # are untouched; the user turn persists for subsequent model calls.
                messages.append({"role":"user","content":instruction})
            self.entered=True
        if self.real_calls>=self.cap:
            self.failure_types.append("provider_call_budget_exhausted")
            self.provider_failure_status_codes.append(None)
            self.provider_failure_codes.append("registered_call_cap")
            self.provider_safe_error_hints.append(None)
            raise RuntimeError("provider_call_budget_exhausted")
        self.real_calls+=1
        started=time.monotonic()
        try:
            # Archived CostBench outputs omit DeepSeek reasoning_content.
            # Thinking-mode tool continuations therefore 400; all arms must
            # explicitly use the same non-thinking mode, without modifying
            # the native CostBench tool execution loop.
            reply=await self.live.chat.completions.create(
                messages=messages,tools=tools,
                extra_body={"thinking":{"type":"disabled"}},
                **kwargs)
        except Exception as exc:
            # Do not save provider response bodies, credentials or detailed URL.
            self.failure_types.append(type(exc).__name__)
            self.provider_failure_status_codes.append(getattr(exc,"status_code",None))
            error_code=None
            safe_hint=None
            response=getattr(exc,"response",None)
            if response is not None:
                try:
                    detail=response.json()
                    error=detail.get("error",{}) if isinstance(detail,dict) else {}
                    error_code=error.get("code") or error.get("type") if isinstance(error,dict) else None
                    raw_message=error.get("message") if isinstance(error,dict) else None
                    if isinstance(raw_message,str):
                        # The provider may echo request fragments in an error.
                        # Retain only printable text, never a key/token.
                        raw_message=raw_message.replace(os.environ.get("DEEPSEEK_API_KEY",""),"[REDACTED]")
                        raw_message=re.sub(r"(?i)(sk-[A-Za-z0-9_-]{8,})","[REDACTED_API_KEY]",raw_message)
                        safe_hint="".join(c for c in raw_message if 32<=ord(c)<=126)[:240]
                except (ValueError,TypeError,AttributeError):
                    pass
            self.provider_failure_codes.append(str(error_code)[:80] if error_code else None)
            self.provider_safe_error_hints.append(safe_hint)
            raise
        finally:
            self.elapsed_seconds+=time.monotonic()-started
        usage=getattr(reply,"usage",None)
        if usage is None:
            self.usage_available=False
        else:
            for field in self.usage:
                value=getattr(usage,field,None)
                if value is None:self.usage_available=False
                else:self.usage[field]+=int(value)
        return reply

def select_pilot_ids(dynamic):
    grouped=defaultdict(list)
    for qid,row in sorted(dynamic.items()):
        if (row.get("block_stats") or {}).get("block_count_agent")==1:
            grouped[row["task"]].append(qid)
    # Eligibility is purely an observed event reached, before any policy outcomes.
    # Exactly three IDs in each of the five official task categories.
    if sorted(grouped)!=sorted(["transportation","accommodation","attraction","dining","shopping"]):
        raise AssertionError("missing CostBench task category")
    pilot={k:sorted(grouped[k])[:3] for k in sorted(grouped)}
    if any(len(ids)!=3 for ids in pilot.values()):raise AssertionError("not enough eligible development tasks")
    return pilot

async def run_case(official,archive,original_query,policy,gate_record,call_cap):
    q=copy.deepcopy(original_query)
    trigger=(archive.get("block_stats") or {})["block_step"][0]
    recorder={"state":[]}
    from env.utils.blocker import DynamicBlocker
    old_set=DynamicBlocker.set_current_state
    def observed_set(self,types):
        recorder["state"].append(frozenset(types))
        return old_set(self,types)
    DynamicBlocker.set_current_state=observed_set
    try:
        from openai import AsyncOpenAI
        async with AsyncOpenAI(base_url="https://api.deepseek.com",
                               api_key=os.environ["DEEPSEEK_API_KEY"],
                               timeout=150.0) as real_client:
            c=ForkedCompletions(archive,trigger,policy,real_client,
                gate_record["tool_state_digest"],
                shared_snapshot=lambda:recorder["state"][-1] if recorder["state"] else [],
                cap=call_cap)
            args=native_args(official,BASE/"inputs/manifest.json")
            seed=official._stable_int(f"42:{q['query_id']}")
            row=await official.run_single_query(OfflineClient(c),q,args,0,seed)
    finally:
        DynamicBlocker.set_current_state=old_set
    if not c.entered:
        status="checkpoint_not_reached"
    elif "provider_call_budget_exhausted" in c.failure_types:
        status="budget_exhausted"
    elif c.failure_types:
        status="provider_error"
    else:
        status="executed"
    return row,c,status

def execution_summary(official,row,track,policy,status,source_digest):
    from env.utils.eval import get_agent_final_answer,check_answer_accuracy
    history=row.get("conversation_history") or []
    answer=get_agent_final_answer(history)
    blocks=row.get("block_stats") or {}
    event_count=int(blocks.get("block_count_agent",0) or 0)
    scenarios=(row.get("groundtruth") or {}).get("scenarios") or []
    try:accepted=bool(check_answer_accuracy(answer,scenarios,event_count))
    except Exception:accepted=False
    tc=sum(len(m.get("tool_calls") or []) for m in history if m.get("role")=="assistant")
    native_outputs=[m.get("content") or "" for m in history if m.get("role")=="tool"]
    after=native_outputs[track.trigger_step:]
    tool_costs=[]
    bad_tool_outputs=0
    for output in after:
        if output.startswith(("[ERROR]","Tool execution failed","Error:")):
            bad_tool_outputs+=1
        matches=re.findall(r"\bCost:\s*([0-9]+(?:\.[0-9]+)?)",output)
        tool_costs.append(float(matches[-1]) if matches else None)
    extra_cost=(round(sum(tool_costs),5) if
        after and all(v is not None for v in tool_costs) else None)
    return {
        "policy":policy,"effective_policy":track.policy_effective,
        "status":status,"query_id":row["query_id"].strip("<>"),
        "checkpoint":source_digest,
        "checkpoint_replayed":track.entered,
        "tool_interface_digest":track.fork_public_tools_sha256,
        "checkpoint_conversation_digest":track.fork_conversation_digest,
        "checkpoint_native_state_digest":track.fork_native_state_digest,
        "provider_calls_after_checkpoint":track.real_calls,
        "provider_usage_after_checkpoint":track.usage if track.usage_available else None,
        "provider_elapsed_seconds_after_checkpoint":round(track.elapsed_seconds,5),
        "provider_failure_types":track.failure_types,
        "provider_failure_status_codes":track.provider_failure_status_codes,
        "provider_failure_codes":track.provider_failure_codes,
        "provider_safe_error_hints":track.provider_safe_error_hints,
        "policy_choice_evidence":track.choice_metrics,
        "native_tool_call_attempts_total":tc,
        "native_tool_call_attempts_post_checkpoint":max(0,tc-track.trigger_step),
        "observed_successful_tool_cost_annotations_post_event":extra_cost,
        "failed_native_tool_outputs_post_event":bad_tool_outputs,
        "goal_state_reached":row.get("is_goal_state") is True,
        "official_effective_event_count":event_count,
        "official_final_answer_accepted":accepted,
        "official_status":row.get("status"),
        "final_answer_present":bool(answer),
        "native_conversation_history":[scrub_message(m) for m in history],
        "original_event_metadata":(row.get("block_stats") or {}).get("metadata",[]),
    }

def write_one(path,payload):
    if path.exists():raise FileExistsError("do not replace an existing policy output")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")

async def main_async(costbench_root,category,out,call_cap,smoke=False):
    if not os.environ.get("DEEPSEEK_API_KEY"):raise RuntimeError("MISSING_DEEPSEEK_API_KEY")
    sys.path.insert(0,str(costbench_root.resolve()))
    import env.run as official
    original=Path.cwd()
    os.chdir(costbench_root)
    try:
        all_q=load_dev80();dynamic=load_dynamic()
        pilot=select_pilot_ids(dynamic)
        replay=json.loads((HERE/"REPLAY_GATE.json").read_text(encoding="utf-8"))
        gates={x["query_id"]:x for x in replay["tasks"]}
        subset=pilot[category][:1] if smoke else pilot[category]
        chosen_policies=("native_continue",) if smoke else POLICIES
        manifest={"schema":"phase2b-native-official-policy-prompt-pilot-v1",
            "frozen_selection":pilot,"category":category,"chosen_ids":subset,
            "integration_smoke_only":smoke,
            "method_scope":"prompt-only interventions after same native CostBench checkpoint",
            "policies":list(chosen_policies),"max_provider_calls_per_arm":call_cap,
            "model":"deepseek-flash","temperature":0,
            "post_checkpoint_thinking_mode":"disabled",
            "reason_for_mode":"official archived tool-call history omits required reasoning_content for thinking-mode continuations",
            "upstream_commit":"6424069f3f773ade076bcedbed302ed47cfb1837",
            "note":"No formal precommitted remaining plan; do not call a prompt variant proven RETAIN or LOCAL_REPAIR."}
        write_one(out/"MANIFEST.json",manifest)
        outputs=[]
        for qid in subset:
            gate=gates[qid]
            if gate["status"]!="replay_matched_checkpoint":
                raise AssertionError("selected task missing successful original-native replay gate")
            # Fixed per-query rotation prevents always running a given policy first.
            rotation=int(hashlib.sha256(qid.encode()).hexdigest()[:8],16)%len(chosen_policies)
            arms=chosen_policies[rotation:]+chosen_policies[:rotation]
            for policy in arms:
                row,track,status=await run_case(official,dynamic[qid],all_q[qid],
                    policy,gate,call_cap)
                result=execution_summary(official,row,track,policy,status,gate["tool_state_digest"])
                outputs.append(result)
                write_one(out/"cases"/qid/(policy+".json"),result)
                if 402 in (result.get("provider_failure_status_codes") or []):
                    write_one(out/"BLOCKED.json",{
                        "status":"DEEPSEEK_ACCOUNT_INSUFFICIENT_BALANCE",
                        "http_code":402,
                        "first_rejected_query_id":qid,
                        "first_rejected_policy":policy,
                        "completed_policy_arm_results":len(outputs),
                        "note":"Stopped immediately after first 402 to prevent repeated rejected calls; no performance claim."
                    })
                    raise RuntimeError("DEEPSEEK_API_HTTP_402_HALT_NO_MORE_CALLS")
        if len(outputs)!=len(subset)*len(chosen_policies):
            raise AssertionError("not all policy outcomes were attempted")
        # All interventions must have the same input state, conversation, and tool snapshot.
        for qid in subset:
            matched=[x for x in outputs if x["query_id"]==qid]
            for key in ["tool_interface_digest","checkpoint_conversation_digest",
                        "checkpoint_native_state_digest"]:
                digests={x[key] for x in matched}
                if len(digests)!=1 or None in digests:
                    raise AssertionError("PAIRED_CHECKPOINT_MISMATCH "+qid+" "+key)
        write_one(out/"RESULTS.json",{"manifest":manifest,"outcomes":outputs})
        print("COSTBENCH_POLICY_PILOT "+json.dumps({
            "category":category,"independent_tasks":len(subset),
            "paired_arms":len(outputs),
            "live_provider_calls":sum(x["provider_calls_after_checkpoint"] for x in outputs),
            "accepted_per_policy":{p:sum(x["official_final_answer_accepted"] for x in outputs if x["policy"]==p) for p in chosen_policies},
        },sort_keys=True))
    finally:
        os.chdir(original)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--category",choices=["transportation","accommodation","attraction","dining","shopping"],required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=4)
    p.add_argument("--integration-smoke",action="store_true",help="one frozen transportation task, native_continue only; not part of scored pilot")
    args=p.parse_args()
    if args.out.exists():raise FileExistsError("one-shot condition output must not preexist")
    if not 1<=args.call_cap<=4:raise ValueError("call-cap is bounded by frozen protocol")
    if args.integration_smoke and args.category!="transportation":
        raise ValueError("integration smoke is frozen to the first eligible transportation task")
    asyncio.run(main_async(args.costbench_root.resolve(),args.category,args.out.resolve(),args.call_cap,args.integration_smoke))

if __name__=="__main__":main()
