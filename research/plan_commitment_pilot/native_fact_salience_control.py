#!/usr/bin/env python3
"""Native Agent information-salience mechanism control, not an algorithm.
Two native task checkpoints, retain/switch facts x low/high factual-explicitness.
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

CASES={
 "Query00271":{"old":"comfort_priority","new":"scenic_route",
     "old_next":["Transportation_Search_Planning_to_Step2","Select_Final_Transportation"],
     "alternative":["Search_Transportation_Candidates","Transportation_Refinement_Step1","Transportation_Refinement_Step2","Select_Final_Transportation"]},
 "Query00306":{"old":"comfort_priority","new":"scenic_route",
     "old_next":["Transportation_Search_Planning_to_Step2","Select_Final_Transportation"],
     "alternative":["Search_Transportation_Candidates","Transportation_Refinement_Step1","Transportation_Refinement_Step2","Select_Final_Transportation"]}
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
                for identity in ("minimal_fact","explicit_temporal_update"):
                    candidate=[]
                    target=case["old"] if condition=="retain" else case["new"]
                    if identity=="minimal_fact":
                        fact=f"Current transportation style preference: {target}. Please complete the existing transportation request."
                    elif condition=="retain":
                        fact=(f"User clarification: the transportation style is still {target}, unchanged from the original user request. "
                              "The earlier preference decision was made under that same style. Please continue the existing task.")
                    else:
                        fact=(f"User correction: the transportation style was {case['old']} when the earlier preference was selected, "
                              f"but the user now requests {case['new']} instead. The previous preference object was produced for the former style. "
                              "Please complete the existing task for the current user request.")
                    reference=""
                    class Fork(oldclass):
                        async def create(self,*,messages,tools,**kwargs):
                            if self.step==self.trigger_step and not self.entered:
                                self.original_digest=digest(messages)
                                self.original_tools_sha=hashlib.sha256(canonical(tools).encode()).hexdigest()
                                offered=[t["function"]["name"] for t in tools]
                                if not all(name in offered for name in case["old_next"]):
                                    raise AssertionError("old continuation must remain publicly executable")
                                messages.append({"role":"user","content":fact})
                                self.intervention_digest=digest(messages)
                            return await super().create(messages=messages,tools=tools,**kwargs)
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
                         "user_fact":fact,**analyze(row,tracker,condition,target)})
                    records.append(result)
                    print("NATIVE_FACT_SALIENCE",qid,condition,identity,
                          result["first_tool"],result["first_action_correct"],status,flush=True)
                    if 402 in (result.get("provider_failure_status_codes") or []):
                        raise RuntimeError("PROVIDER_402_STOP")
            this=[x for x in records if x["task"]==qid]
            if len(this)!=4:raise AssertionError("Incomplete task pair")
            for field in ("original_checkpoint_digest","checkpoint_native_state_digest","tool_interface_digest","original_tools_digest"):
                assert len({x.get(field) for x in this})==1,(qid,field)
        data={"schema":"native-fact-update-salience-causal-contrast-v1",
            "independent_development_tasks":len(CASES),"correlated_continuations":len(records),
            "total_provider_calls":sum(x["provider_calls_after_checkpoint"] for x in records),
            "question":"Do matched current style facts produce different Agent actions when the temporal relation to the previous preference is explicit versus implicit?",
            "boundaries":["No competing path is suggested; only wording about the relationship between the old and new fact changes.",
              "Native state and old style objects are not semantically invalidated. Evaluate corrected first tool argument, not stale official answer scorer.",
              "This is a development-only behavioral intervention. No inference about model internal psychology.",
              "These are prompts about user preference facts; external semantic fulfillment remains unverified by upstream goal checker."],
            "results":records}
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(data,indent=2,ensure_ascii=False,sort_keys=True,default=str)+"\n",encoding="utf-8")
        print("NATIVE_FACT_SALIENCE_SUMMARY",json.dumps({
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
    if not 1<=a.call_cap<=4:raise ValueError("max 4 model calls per continuation")
    asyncio.run(execute(a.costbench_root.resolve(),a.out.resolve(),a.call_cap))
