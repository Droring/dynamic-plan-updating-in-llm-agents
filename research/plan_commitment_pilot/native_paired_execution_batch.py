#!/usr/bin/env python3
"""Three additional native paired availability cases, original development tasks.
Reuses the audited four-arm runner, and writes one task file before proceeding.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import native_paired_removal as native

CASES={
 "Query00261":{
  "incumbent":"Transportation_Refine_to_Step2",
  "unrelated":"Transportation_Finish_from_Step1_3Steps",
  "old":"The lowest-cost path is **AB → CD → E**, so I’ll use the combined preference/search tool, followed by the combined two-stage refinement tool, then final selection.",
  "neutral":"An available path is AB → CD → E: combined preference/search, combined two-stage refinement, then final selection."},
 "Query00249":{
  "incumbent":"Transportation_Search_to_Final_4Steps",
  "unrelated":"Transportation_Search_Planning_to_Step2",
  "old":"**Lowest cost = Path 15 (A → BCDE) at 100.62.** I'll first decide the preference (A), then use BCDE to search, refine, and select in one call.",
  "neutral":"One available route is Path 15 (A → BCDE): first decide preference (A), followed by BCDE search, refinement and selection."},
 "Query00306":{
  "incumbent":"Transportation_Search_Planning_to_Step2",
  "unrelated":"Transportation_Search_to_Final_4Steps",
  "old":"The lowest-cost path is A → BCD → E: decide the preference, search and refine through availability and convenience with the composite tool, then select the final option.",
  "neutral":"An available route is A → BCD → E: preference decision, a composite search and refinement, and final selection."}
}
async def run(root,outdir,preflight,cap):
    if outdir.exists():raise FileExistsError("do not overwrite prior batch")
    outdir.mkdir(parents=True)
    manifest={"independent_development_tasks":len(CASES),
      "tasks":list(CASES),"four_correlated_arms_per_task":True,
      "preflight":preflight,"max_provider_calls_per_arm":cap,
      "upstream":"official-native-CostBench-6424069f3f773ade076bcedbed302ed47cfb1837",
      "warning":"Exploratory development task action-choice sensitivity, not heldout generalization or cost optimization."}
    (outdir/"MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    for qid,case in CASES.items():
        native.TASK=qid
        native.INCUMBENT=case["incumbent"]
        native.UNRELATED=case["unrelated"]
        native.PLAN_OLD=case["old"]
        native.PLAN_NEUTRAL=case["neutral"]
        await native.experiment(root,(outdir/(qid+".json")).resolve(),cap,preflight)
    print("THREE_TASK_NATIVE_BATCH_COMPLETE",json.dumps(manifest))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--call-cap",type=int,default=5)
    args=p.parse_args()
    # The underlying run's original three-call bound is a technical limit,
    # not a hard methodological bound; increase to a fixed maximum of five.
    if not 1<=args.call_cap<=5:raise ValueError("maximum five calls per arm")
    asyncio.run(run(args.costbench_root.resolve(),args.out_dir.resolve(),args.preflight,args.call_cap))
