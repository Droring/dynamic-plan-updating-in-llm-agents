#!/usr/bin/env python3
"""Minimal-fact four-task native plan-authorship contrast.
Same original executed native checkpoint and same new fact within a task;
only the Agent's own prospective plan wording is neutralized vs preserved.
"""
from pathlib import Path
import argparse
import asyncio
import json
import native_fact_revision as fact
from native_fact_update_batch import CASES as OTHER
CASES={
 "Query00271":{
 "old_style":"comfort_priority","new_style":"scenic_route",
 "next":"Transportation_Search_Planning_to_Step2",
 "plan":"I’ll use the atomic preference decision first, then the cheapest composite covering search plus both refinement steps, followed by the final selection.",
 "neutral":"One possible tool sequence is preference decision, followed by composite search and refinement, then final selection."},
 **OTHER
}
async def run(root,outdir,cap):
    if outdir.exists():raise FileExistsError("no output overwrite or outcome-dependent retry")
    outdir.mkdir(parents=True)
    (outdir/"LOCK.json").write_text(json.dumps({
      "schema":"four-task-native-minimal-fact-ownership-control-v1",
      "base_task_ids":list(CASES),"tasks":4,"correlated_arms":16,
      "interventions":["retain","switch"],"plan_history":["committed","neutralized"],
      "note":"old user request and tool prefix frozen, factual update is a minimal current style statement; no alternative or explicit old-result invalidation supplied",
      "warning":"neutralization changes authorial wording, not removing the old plan or its native tool history",
      "provider_call_cap_per_arm":cap},indent=2)+"\n")
    for q,c in CASES.items():
        fact.QID=q
        fact.PLAN=c["plan"]
        fact.NEUTRAL=c["neutral"]
        fact.NEXT=c["next"]
        fact.FACTS={
         "retain":f"Current transportation style preference: {c['old_style']}. Please complete the existing transportation request.",
         "switch":f"Current transportation style preference: {c['new_style']}. Please complete the existing transportation request."
        }
        await fact.execute(root,(outdir/(q+".json")).resolve(),cap)
    print("MINIMAL_FACT_OWNERSHIP_FOUR_TASKS_COMPLETE",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=5)
    a=p.parse_args()
    if not 1<=a.call_cap<=5:raise ValueError("max five provider calls/arm")
    asyncio.run(run(a.costbench_root.resolve(),a.out_dir.resolve(),a.call_cap))
