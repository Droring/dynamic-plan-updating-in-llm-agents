#!/usr/bin/env python3
"""Native Agent: compare minimal user fact, explicit delta baseline, and EDR derived from tool provenance.
Four native task checkpoints, matched retain/switch facts x three policies.
No replacement plan, no required tool name and no oracle action shown to the model.
"""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PHASE=ROOT/"research/costbench_method_studies/plan_commitment_evidence_gate"
sys.path.insert(0,str(PHASE))
import policy_pilot as pilot
from replay_gate import load_dev80,load_dynamic,canonical

from evidence_dependency_refresh import build_ledger
from action_evidence_guard import extract_calls, inspect_action, correction_for, PREFERENCE_PRODUCERS
CASES={
 "Query00271":{"old":"comfort_priority","new":"scenic_route",
     "old_next":["Transportation_Search_Planning_to_Step2","Select_Final_Transportation"]},
 "Query00306":{"old":"comfort_priority","new":"scenic_route",
     "old_next":["Transportation_Search_Planning_to_Step2","Select_Final_Transportation"]},
 "Query00261":{"old":"scenic_route","new":"comfort_priority",
     "old_next":["Transportation_Refine_to_Step2","Select_Final_Transportation"]},
 "Query00249":{"old":"scenic_route","new":"comfort_priority",
     "old_next":["Transportation_Search_to_Final_4Steps"]}
}
PREFTOOLS={"Decide_Transportation_Preference","Transportation_Preference_and_Search",
           "Transportation_Full_Planning_to_Step1","Transportation_Full_Planning_to_Step2"}
def digest(ms):return hashlib.sha256(canonical([pilot.scrub_message(x) for x in ms]).encode()).hexdigest()
def getname(call):
    if isinstance(call,dict):return call.get("name") or (call.get("function") or {}).get("name")
    return getattr(call,"name",None) or getattr(getattr(call,"function",None),"name",None)
def getargs(call):
    if isinstance(call,dict):data=call.get("arguments") or (call.get("function") or {}).get("arguments") or "{}"
    else:data=getattr(call,"arguments",None) or getattr(getattr(call,"function",None),"arguments","{}")
    try:return json.loads(data) if isinstance(data,str) else (data or {})
    except Exception:return {}
def analyze(row,tracker,condition,target):
    assistant=[m for m in row.get("conversation_history",[]) if m.get("role")=="assistant"]
    post=assistant[tracker.trigger_step:]
    calls=[{"name":getname(x),"args":getargs(x)} for m in post for x in m.get("tool_calls") or []]
    first=calls[0] if calls else {}
    first_pref=first.get("name") in PREFTOOLS and first.get("args",{}).get("TransportationStyle")==target
    # A correct RETAIN can continue from a previously produced valid preference
    # without needlessly recomputing the unchanged first stage.
    first_correct=first_pref if condition=="switch" else bool(first) and first.get("name") not in PREFTOOLS
    return {"first_tool":first.get("name"),"first_arguments":first.get("args"),
         "first_action_correct":bool(first_correct),
         "all_post_event_calls":calls,
         "recomputed_preference_after_event":any(c["name"] in PREFTOOLS for c in calls),
         "first_uses_updated_style":bool(first_pref)}

async def execute(root,out,cap):
    if out.exists():raise FileExistsError("Do not overwrite prior evidence.")
    if not os.environ.get("DEEPSEEK_API_KEY"):raise RuntimeError("Missing DEEPSEEK_API_KEY")
    import importlib
    sys.path.insert(0,str(root))
    official=importlib.import_module("env.run")
    oldcwd=Path.cwd();os.chdir(root)
    oldclass=pilot.ForkedCompletions
    records=[]
    try:
        archive=load_dynamic();dev=load_dev80()
        gates={x["query_id"]:x for x in json.loads((PHASE/"REPLAY_GATE.json").read_text())["tasks"]}
        for qid,case in CASES.items():
            gate=gates[qid]
            assert gate["status"]=="replay_matched_checkpoint"
            for condition in ("retain","switch"):
                for identity in ("minimal_fact","explicit_delta_baseline","action_guard"):
                    candidate=[]
                    target=case["old"] if condition=="retain" else case["new"]
                    fact=f"Current transportation style preference: {target}. Please complete the existing transportation request."
                    if identity=="explicit_delta_baseline":
                        fact=(f"User correction: transportation style has changed from {case['old']} to {target}. "
                              "Please complete the existing transportation request.") if condition=="switch" else (
                              f"User confirmation: transportation style remains {target}, unchanged. "
                              "Please complete the existing transportation request.")
                    reference=""
                    class Fork(oldclass):
                        async def create(self,*,messages,tools,**kwargs):
                            if self.step==self.trigger_step and not self.entered:
                                self.original_digest=digest(messages)
                                self.original_tools_sha=hashlib.sha256(canonical(tools).encode()).hexdigest()
                                offered=[t["function"]["name"] for t in tools]
                                if not all(name in offered for name in case["old_next"]):
                                    raise AssertionError("old continuation must remain publicly executable")
                                self.edr_ledger=None
                                if identity=="action_guard":
                                    self.edr_ledger=build_ledger(messages,fact,[],tools)
                                    if self.edr_ledger["status"]=="unknown":
                                        raise AssertionError("EDR cannot infer previous tool-argument lineage; no unknown-case oracle substitution")
                                messages.append({"role":"user","content":fact})
                                if identity=="action_guard":
                                    self.guard_rejections=0
                                    self.guard_feedback_calls=0
                                    self.fresh_preference_observed=False
                                self.intervention_digest=digest(messages)
                            reply=await super().create(messages=messages,tools=tools,**kwargs)
                            if identity!="action_guard" or not self.entered:
                                return reply
                            def violations_for(proposed):
                                return inspect_action(extract_calls(proposed),tools,
                                    self.state_supplier(),self.edr_ledger,
                                    has_refreshed=self.fresh_preference_observed)
                            violations=violations_for(reply)
                            if violations:
                                if self.guard_rejections>=1:
                                    raise RuntimeError("guard_max_rejections_pre_action")
                                self.guard_rejections+=1
                                self.guard_feedback_calls+=1
                                # The rejected tool action is NOT executed. A
                                # single feedback-only model call is charged.
                                feedback=correction_for(violations)
                                retry_messages=list(messages)+[{"role":"user","content":feedback}]
                                reply=await super().create(messages=retry_messages,tools=tools,**kwargs)
                                again=violations_for(reply)
                                if again:
                                    self.guard_rejections+=1
                                    raise RuntimeError("guard_second_attempt_invalid_no_tool_execution")
                            if self.edr_ledger["status"]=="changed":
                                for proposed in extract_calls(reply):
                                    if (proposed["tool"] in PREFERENCE_PRODUCERS and
                                        proposed["arguments"].get("TransportationStyle")==self.edr_ledger["new_style"]):
                                        self.fresh_preference_observed=True
                            return reply
                    pilot.ForkedCompletions=Fork
                    try:
                        row,tracker,status=await pilot.run_case(
                            official,archive[qid],dev[qid],"native_continue",gate,cap)
                    finally:pilot.ForkedCompletions=oldclass
                    result=pilot.execution_summary(official,row,tracker,identity,status,gate["tool_state_digest"])
                    result.update({"task":qid,"fact_condition":condition,"factual_explicitness":identity,
                         "target_style":target,
                         "original_checkpoint_digest":getattr(tracker,"original_digest",None),
                         "original_tools_digest":getattr(tracker,"original_tools_sha",None),
                         "intervention_digest":getattr(tracker,"intervention_digest",None),
                         "user_fact":fact, "edr_ledger":getattr(tracker,"edr_ledger",None),
                         "action_guard_rejections":getattr(tracker,"guard_rejections",0),
                         "action_guard_feedback_calls":getattr(tracker,"guard_feedback_calls",0), **analyze(row,tracker,condition,target)})
                    records.append(result)
                    print("NATIVE_ACTION_GUARD",qid,condition,identity,
                          result["first_tool"],result["first_action_correct"],status,flush=True)
                    if 402 in (result.get("provider_failure_status_codes") or []):
                        raise RuntimeError("PROVIDER_402_STOP")
            this=[x for x in records if x["task"]==qid]
            if len(this)!=6:raise AssertionError("Incomplete three-policy task")
            for field in ("original_checkpoint_digest","checkpoint_native_state_digest","tool_interface_digest","original_tools_digest"):
                assert len({x.get(field) for x in this})==1,(qid,field)
        data={"schema":"native-action-evidence-guard-three-policy-development-v1",
            "independent_development_tasks":len(CASES),"correlated_continuations":len(records),
            "total_provider_calls":sum(x["provider_calls_after_checkpoint"] for x in records),
            "question":"Does rejecting unsupported native tool actions before execution improve outcome versus minimal fact and explicit-change baselines?",
            "boundaries":["No competing path is suggested. Action guard derives provenance from prior tool arguments and rejects unsupported pre-action tool calls with at most one feedback retry. It sees no gold label.",
              "Native state and old style objects are not semantically invalidated. Evaluate corrected first tool argument, not stale official answer scorer.",
              "This is a development-only behavioral intervention. No inference about model internal psychology.",
              "These are prompts about user preference facts; external semantic fulfillment remains unverified by upstream goal checker."],
            "results":records}
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(data,indent=2,ensure_ascii=False,sort_keys=True,default=str)+"\n",encoding="utf-8")
        print("NATIVE_ACTION_GUARD_SUMMARY",json.dumps({
            "base_tasks":len(CASES),"arms":len(records),"calls":data["total_provider_calls"],
            "correct":sum(x["first_action_correct"] for x in records)},sort_keys=True),flush=True)
    finally:
        pilot.ForkedCompletions=oldclass
        os.chdir(oldcwd)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=4)
    a=p.parse_args()
    if not 1<=a.call_cap<=5:raise ValueError("max 5 model calls per continuation")
    asyncio.run(execute(a.costbench_root.resolve(),a.out.resolve(),a.call_cap))
