#!/usr/bin/env python3
"""Independent native EDR method evaluation from original archived 24 tool histories.
Count tool errors, cap exhaustion, first tool validity, and old/new preference
argument correctness independently. Never use stale official answer scorer.
"""
import json,argparse
from collections import defaultdict
from pathlib import Path
from audit_fact_salience import get_first_tool_result
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/"evidence/NATIVE_EDR_POLICY.json"
def score():
    data=json.loads(SOURCE.read_text())
    assert data["independent_development_tasks"]==4 and data["correlated_continuations"]==24
    rows=[]
    group=defaultdict(list)
    for z in data["results"]:
        first=get_first_tool_result(z)
        good=bool(z["first_action_correct"] and not first["error"])
        rec={"task":z["task"],"fact":z["fact_condition"],"policy":z["factual_explicitness"],
            "decision_correct":bool(z["first_action_correct"]),
            "first_tool_valid":not first["error"],"first_tool_and_decision_correct":good,
            "native_goal_state_reached":bool(z["goal_state_reached"]),
            "no_post_event_tool_error":z["failed_native_tool_outputs_post_event"]==0,
            "trajectory_completed":z["status"]=="executed",
            "complete_no_error":z["status"]=="executed" and z["goal_state_reached"] and z["failed_native_tool_outputs_post_event"]==0,
            "api_calls":z["provider_calls_after_checkpoint"],
            "ledger_status":z["edr_ledger"]["status"] if z.get("edr_ledger") else None}
        group[(rec["policy"],rec["fact"])].append(rec);rows.append(rec)
    assert len(group)==6
    table={}
    for key,items in sorted(group.items()):
        assert len(items)==4
        policy,fact=key
        table[f"{policy}__{fact}"]={
            "n_tasks":len(items),"first_decision_correct":sum(x["decision_correct"] for x in items),
            "first_tool_valid":sum(x["first_tool_valid"] for x in items),
            "first_decision_and_valid":sum(x["first_tool_and_decision_correct"] for x in items),
            "goal_type_reached":sum(x["native_goal_state_reached"] for x in items),
            "complete_without_tool_errors":sum(x["complete_no_error"] for x in items),
            "provider_calls":sum(x["api_calls"] for x in items)}
    for q in set(x["task"] for x in rows):
        items=[x for x in data["results"] if x["task"]==q]
        assert len(items)==6
        for field in ("checkpoint_native_state_digest","tool_interface_digest","original_checkpoint_digest"):
            assert len({y[field] for y in items})==1,(q,field)
    return {"schema":"edr-native-three-arm-independent-audit-v1",
        "independent_development_tasks":4,"correlated_arms":24,
        "total_model_calls":sum(x["api_calls"] for x in rows),
        "table":table,"records":rows,
        "limits":["EDR produces a model-visible evidence ledger from observed prior tool arguments and new factual value; it does not enforce action correctness.",
                  "The official CostBench semantic goal checker is not updated to the new user preference.",
                  "This is the same four exploratory development tasks used in the previous mechanism discovery.",
                  "First action correctness is not full task completion; budget-exhausted runs count as not completed.",
                  "A generic explicit old-new prompt baseline performs equally well on first action and cannot be omitted from method comparison."]}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=score();a.out.parent.mkdir(parents=True,exist_ok=True)
    if a.out.exists():raise FileExistsError("do not overwrite evidence")
    a.out.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
    print("EDR_NATIVE_AUDIT "+json.dumps({"tasks":x["independent_development_tasks"],"arms":x["correlated_arms"],"table":x["table"]},sort_keys=True))
