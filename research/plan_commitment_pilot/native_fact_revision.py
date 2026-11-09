#!/usr/bin/env python3
"""Native same-checkpoint updated user-fact pilot; four DeepSeek tool continuations.
This tests observable action after a preference correction, NOT true state invalidation.
"""
from __future__ import annotations
import asyncio, argparse, hashlib, json, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PHASE=HERE.parents[1]/"research/costbench_method_studies/plan_commitment_evidence_gate"
sys.path.insert(0,str(PHASE))
import policy_pilot as pilot
from replay_gate import load_dev80,load_dynamic,canonical

QID="Query00271"
PLAN="I’ll use the atomic preference decision first, then the cheapest composite covering search plus both refinement steps, followed by the final selection."
NEUTRAL="One possible tool sequence is preference decision, followed by composite search and refinement, then final selection."
DECIDE="Decide_Transportation_Preference"
NEXT="Transportation_Search_Planning_to_Step2"
FACTS={
  "retain":"Clarification from the user: My transportation style remains comfort_priority. The earlier chosen preference is still correct. Please continue the task.",
  "switch":"Correction from the user: My transportation style is now scenic_route, NOT comfort_priority. The earlier preference result reflects the old request. Please complete the task using the corrected preference."
}
def digest(messages):
    return hashlib.sha256(canonical([pilot.scrub_message(x) for x in messages]).encode()).hexdigest()
def name(call):
    if isinstance(call,dict):
        f=call.get("function") or {}
        return call.get("name") or (f.get("name") if isinstance(f,dict) else getattr(f,"name",None))
    return getattr(call,"name",None) or getattr(getattr(call,"function",None),"name",None)
async def execute(root,out,cap):
    if not os.environ.get("DEEPSEEK_API_KEY"):raise RuntimeError("DEEPSEEK_API_KEY missing")
    if out.exists():raise FileExistsError("do not overwrite previous evidence")
    sys.path.insert(0,str(root.resolve()))
    import env.run as official
    original=Path.cwd()
    os.chdir(root.resolve())
    original_class=pilot.ForkedCompletions
    rows=[]
    try:
        dev=load_dev80(); archives=load_dynamic()
        gate={g["query_id"]:g for g in json.loads((PHASE/"REPLAY_GATE.json").read_text())["tasks"]}[QID]
        assert gate["status"]=="replay_matched_checkpoint"
        for event in ("retain","switch"):
            for context in ("committed","neutralized"):
                class FactFork(original_class):
                    async def create(self,*,messages,tools,**kwargs):
                        if self.step==self.trigger_step and not self.entered:
                            self.original_checkpoint_hash=digest(messages)
                            if context=="neutralized":
                                matches=[m for m in messages if m.get("role")=="assistant" and PLAN in (m.get("content") or "")]
                                if len(matches)!=1:raise AssertionError("prospective self plan missing")
                                matches[0]["content"]=matches[0]["content"].replace(PLAN,NEUTRAL,1)
                            self.context_pre_event_hash=digest(messages)
                            # Same executed prefix, explicit corrected user fact.
                            messages.append({"role":"user","content":FACTS[event]})
                        return await super().create(messages=messages,tools=tools,**kwargs)
                pilot.ForkedCompletions=FactFork
                try:
                    row,track,status=await pilot.run_case(official,archives[QID],dev[QID],
                        "native_continue",gate,cap)
                finally:
                    pilot.ForkedCompletions=original_class
                rec=pilot.execution_summary(official,row,track,context,status,gate["tool_state_digest"])
                assistants=[m for m in (row.get("conversation_history") or []) if m.get("role")=="assistant"]
                post=assistants[track.trigger_step:]
                first=[name(c) for c in ((post[0].get("tool_calls") or []) if post else [])]
                allcalls=[name(c) for m in post for c in (m.get("tool_calls") or [])]
                rec.update({"fact_condition":event,"commitment_condition":context,
                    "first_action":first,"all_post_event_actions":allcalls,
                    "did_redo_preference":DECIDE in allcalls,
                    "did_continue_old_next_tool":NEXT in first,
                    "original_checkpoint_hash":getattr(track,"original_checkpoint_hash",None),
                    "context_pre_event_hash":getattr(track,"context_pre_event_hash",None),
                    "event_user_message":FACTS[event]})
                rows.append(rec)
                if 402 in (rec.get("provider_failure_status_codes") or []):
                    raise RuntimeError("DEEPSEEK_API_HTTP_402_STOP")
        if len(rows)!=4:raise AssertionError("missing an arm")
        for field in ("original_checkpoint_hash","checkpoint_native_state_digest","tool_interface_digest"):
            vals={v.get(field) for v in rows}
            if len(vals)!=1 or None in vals:raise AssertionError("different original checkpoint "+field)
        result={"schema":"preference-fact-revision-native-v1",
            "base_tasks":1,"correlated_arms":4,"provider_calls":sum(v["provider_calls_after_checkpoint"] for v in rows),
            "event_conditions":["retain","switch"],"context_conditions":["committed","neutralized"],
            "warning":"A newly supplied user correction changes the target preference but the original CostBench state retains its historical type instances. Goal-state and official-final-answer acceptance are NOT gold semantic-update labels. Redoing preference with corrected argument must be audited.",
            "results":rows}
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True,default=str)+"\n")
        print("FACT_REVISION_NATIVE "+json.dumps({
            "calls":result["provider_calls"],
            "actions":[(v["fact_condition"],v["commitment_condition"],v["first_action"],v["did_redo_preference"],v["status"]) for v in rows]}))
    finally:
        pilot.ForkedCompletions=original_class
        os.chdir(original)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=5)
    a=p.parse_args()
    if not 1<=a.call_cap<=5:raise ValueError("provider call cap must be <=5")
    asyncio.run(execute(a.costbench_root.resolve(),a.out.resolve(),a.call_cap))
