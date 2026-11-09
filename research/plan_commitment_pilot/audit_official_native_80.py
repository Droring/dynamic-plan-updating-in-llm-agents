#!/usr/bin/env python3
"""Independent 80-task paired original-native static/dynamic outcome audit.

Official original final-answer evaluator only; NOT true replanning decision
correctness and NOT semantic preference update testing.
"""
import json
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"research/costbench_method_studies/official_dev_baseline/evidence/results"
OUT=ROOT/"research/plan_commitment_pilot/evidence/OFFICIAL_NATIVE_80_PAIRED_OUTCOMES.json"
def read(group,name):
    o={}
    for i in range(4):
        p=BASE/group/f"shard{i:02d}"/name
        j=json.loads(p.read_text(encoding="utf8"))
        for x in j["results"]:
            q=x["query_id"].strip("<>")
            assert q not in o
            o[q]=x
    assert len(o)==80
    return o
def main():
    a=read("static","results_deepseek-flash_unblocked_refinement_2.json")
    b=read("official_cost_change","results_deepseek-flash_blocked-cost_change-1_refinement_2.json")
    assert set(a)==set(b)
    counters=Counter()
    categories=defaultdict(Counter)
    records=[]
    for q in sorted(a):
        x,y=a[q],b[q]
        assert x["task"]==y["task"]
        sx=bool((x.get("evaluation") or {}).get("success"))
        sy=bool((y.get("evaluation") or {}).get("success"))
        observed=(y.get("block_stats") or {}).get("block_count_agent")==1
        key=("correct" if sx else "incorrect")+"__"+("correct" if sy else "incorrect")
        counters[key]+=1
        counters["static_correct"]+=sx
        counters["dynamic_correct"]+=sy
        counters["observed_dynamic_event"]+=observed
        categories[x["task"]][key]+=1
        records.append({"query_id":q,"task":x["task"],
            "static_official_answer_correct":sx,
            "dynamic_official_answer_correct":sy,
            "native_dynamic_event_observed":observed,
            "native_checkpoint_replicated":observed,
            "outcome_transition":key,
            "not_a_plan_retain_switch_label":True})
    assert counters["static_correct"]==70 and counters["dynamic_correct"]==60
    assert counters["observed_dynamic_event"]==67
    out={"schema":"native-dev80-static-dynamic-paired-original-evaluator-v1",
     "independent_base_tasks":80,
     "counters":dict(counters),
     "by_category":{k:dict(v) for k,v in sorted(categories.items())},
     "records":records,
     "limitations":["All 80 tasks share a dev80 selection and original official native runner, not prospective heldout 20 task replication.",
       "Original static/dynamic evaluations are not a controlled RETAIN-versus-SWITCH action intervention.",
       "Official final-answer correctness does NOT mean the model correctly decided whether to preserve its plan.",
       "No new paid API calls were needed to audit this evidence."]}
    if OUT.exists():raise FileExistsError("already audited")
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf8")
    print("ORIGINAL_80_PAIRED_AUDIT",json.dumps({"n":80,"counters":out["counters"],"by_category":out["by_category"]},sort_keys=True))
if __name__=="__main__":main()
