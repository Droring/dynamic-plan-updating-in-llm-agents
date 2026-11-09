#!/usr/bin/env python3
"""Development-only repeat of real user factual correction under native Agent.
Four arms/task: retain or change preference fact x preserved or neutralized self-plan.
"""
import argparse,asyncio,json
from pathlib import Path
import native_fact_revision as fact

CASES={
 "Query00261":{
  "old_style":"scenic_route","new_style":"comfort_priority",
  "next":"Transportation_Refine_to_Step2",
  "plan":"The lowest-cost path is **AB → CD → E**, so I’ll use the combined preference/search tool, followed by the combined two-stage refinement tool, then final selection.",
  "neutral":"A possible sequence is preference/search, followed by combined refinement, then final selection."},
 "Query00249":{
  "old_style":"scenic_route","new_style":"comfort_priority",
  "next":"Transportation_Search_to_Final_4Steps",
  "plan":"**Lowest cost = Path 15 (A → BCDE) at 100.62.** I'll first decide the preference (A), then use BCDE to search, refine, and select in one call.",
  "neutral":"One possible path is A → BCDE, consisting of preference decision then composite search/refinement/final selection."},
 "Query00306":{
  "old_style":"comfort_priority","new_style":"scenic_route",
  "next":"Transportation_Search_Planning_to_Step2",
  "plan":"The lowest-cost path is A → BCD → E: decide the preference, search and refine through availability and convenience with the composite tool, then select the final option.",
  "neutral":"One possible route is A → BCD → E, consisting of preference, composite search/refinement, then final selection."}
}
async def batch(root,out,cap):
    if out.exists():raise FileExistsError("output folder must be new")
    out.mkdir(parents=True)
    (out/"MANIFEST.json").write_text(json.dumps({"tasks":list(CASES),"independent_tasks":3,
      "correlated_arms_per_task":4,"max_calls_per_arm":cap,
      "scope":"native Agent factual preference correction: executable historical plan, semantically obsolete preference"},indent=2)+"\n")
    for q,c in CASES.items():
        fact.QID=q
        fact.PLAN=c["plan"]
        fact.NEUTRAL=c["neutral"]
        fact.NEXT=c["next"]
        fact.FACTS={
          "retain":f"Clarification from the user: My transportation style remains {c['old_style']}. The earlier chosen preference is still correct. Please continue the task.",
          "switch":f"Correction from the user: My transportation style is now {c['new_style']}, NOT {c['old_style']}. The earlier preference result reflects the old request. Please complete the task using the corrected preference."}
        await fact.execute(root,(out/(q+".json")).resolve(),cap)
    print("FACT_UPDATE_BATCH3_COMPLETED")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=5)
    a=p.parse_args()
    if not 1<=a.call_cap<=5:raise ValueError("cap <=5")
    asyncio.run(batch(a.costbench_root.resolve(),a.out_dir.resolve(),a.call_cap))
