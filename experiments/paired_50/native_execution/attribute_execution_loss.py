#!/usr/bin/env python3
"""Attribute realized native full-trajectory loss to the exact action step.

OFFLINE ONLY. Each V*(s) is recomputed from the reconstructed *post-action*
type-state, using an information-matched exhaustive graph planner. The native
reference solver is never used by a decision policy. This report is diagnostic.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import graph_planning_baseline as graph
import run_bounded_verifier_confirmation as confirmation

TOL = 1e-5
COHORT = {"Query00178","Query00351","Query00549","Query00689","Query00851"}
POLICIES = {"incumbent","candidate_gate","graph_planner"}


def value_after_state(prepared, state):
    result = graph.shortest_feasible_path({**prepared, "state": set(state)})
    if result is None:
        raise ValueError("Reconstructed actual state has no feasible completion")
    return float(result[0])


def attribute_one(record, prepared):
    if not record.get("reached_goal") or len(record.get("steps", [])) == 0:
        raise ValueError("Only fully successful archived trajectories supported")
    if record["checkpoint_sha256"] != prepared["checkpoint_sha256"]:
        raise ValueError("Checkpoint hash does not match frozen CostBench task")
    if record["path"] != [s["tool"] for s in record["steps"]]:
        raise ValueError("Path does not match recorded step sequence")
    state = set(prepared["state"])
    original_state = sorted(state)
    previous_value = value_after_state(prepared, state)
    first_value = previous_value
    if abs(previous_value - record["reference_value"]) > TOL:
        raise ValueError("Initial V*(s) disagrees with official native reference")
    steps = []
    seen_names = set()
    for idx, step in enumerate(record["steps"], 1):
        name = step["tool"]
        tool = prepared["tool_objects"].get(name)
        if tool is None or not step["success"]:
            raise ValueError("Unknown or unsuccessful native tool step")
        if not set(tool.input_types).issubset(state):
            raise ValueError("Actually executed action lacks necessary type-state inputs")
        if abs(float(step["cost"])-float(tool.cost))>TOL:
            raise ValueError("Observed actual step value differs from reconstructed tool")
        if not isinstance(step.get("output"), str) or not step["output"]:
            raise ValueError("Native execution response missing")
        prior = sorted(state)
        adds_type = tool.output_type not in state
        state.add(tool.output_type)
        next_value = value_after_state(prepared,state)
        delta = float(step["cost"]) + next_value - previous_value
        if delta < -TOL:
            raise ValueError("Negative Bellman loss: reconstructed state/value inconsistent")
        steps.append({
            "step":idx, "tool":name,
            "state_before":prior, "state_after":sorted(state),
            "observed_tool_result":step["output"],
            "adds_new_type":adds_type,
            "repeats_tool_name":name in seen_names,
            "action_value":float(step["cost"]),
            "V_before":round(previous_value,8),
            "V_after":round(next_value,8),
            "bellman_loss":round(max(0.0,delta),8),
            "positive_loss":delta>TOL,
        })
        previous_value = next_value
        seen_names.add(name)
    if prepared["goal_type"] not in state:
        raise ValueError("Archived result claims goal without a goal type in actual state")
    if abs(previous_value)>TOL:
        raise ValueError("Terminal typed state should have V*(goal)=0")
    telescoping = sum(s["bellman_loss"] for s in steps)
    actual_regret = float(record["path_regret"])
    if abs(telescoping-actual_regret)>TOL:
        raise ValueError(f"Telescoping failed: {telescoping} vs {actual_regret}")
    positive = [s for s in steps if s["positive_loss"]]
    return {
        "query_id":record["query_id"],
        "environment":record["environment"],
        "policy":record["policy"],
        "checkpoint_sha256":record["checkpoint_sha256"],
        "initial_type_state":original_state,
        "goal_reached":True,
        "steps_executed":len(steps),
        "first_positive_loss_step":positive[0]["step"] if positive else None,
        "first_positive_loss_action":positive[0]["tool"] if positive else None,
        "first_action_loss":steps[0]["bellman_loss"],
        "later_action_loss":round(sum(s["bellman_loss"] for s in steps[1:]),8),
        "total_bellman_loss":round(telescoping,8),
        "recorded_path_regret":actual_regret,
        "positive_loss_steps":len(positive),
        "repeated_tool_names":sum(s["repeats_tool_name"] for s in steps),
        "nonproductive_type_repeats":sum(not s["adds_new_type"] for s in steps),
        "steps":steps,
    }


def analyze(records, checkpoints):
    by_key={(t["query_id"],t["environment_condition"]):t["prepared"] for t in checkpoints}
    if len(by_key)!=20:
        raise ValueError("Expected exactly 20 frozen original type-state checkpoints")
    if len(records)!=30:
        raise ValueError("Expected exactly 30 archived native trajectories")
    ids=set()
    output=[]
    for record in records:
        key=(record["query_id"],record["environment"])
        if record["query_id"] not in COHORT or record["policy"] not in POLICIES:
            raise ValueError("Unfrozen task/policy in native continuation")
        rid=key+(record["policy"],)
        if rid in ids:
            raise ValueError("Duplicate native continuation")
        ids.add(rid)
        output.append(attribute_one(record,by_key[key]))
    if len(ids)!=30:
        raise ValueError("Missing paired native continuation")
    output.sort(key=lambda r:(r["query_id"],r["environment"],r["policy"]))
    summary={}
    for arm in sorted(POLICIES):
        rows=[r for r in output if r["policy"]==arm]
        summary[arm]={
            "n":len(rows),
            "first_step_positive":sum(r["first_action_loss"]>TOL for r in rows),
            "later_steps_positive":sum(r["later_action_loss"]>TOL for r in rows),
            "first_loss_sum":round(sum(r["first_action_loss"] for r in rows),8),
            "later_loss_sum":round(sum(r["later_action_loss"] for r in rows),8),
            "total_loss_sum":round(sum(r["total_bellman_loss"] for r in rows),8),
            "first_loss_step_counts":{
                str(step):sum(r["first_positive_loss_step"]==step for r in rows)
                for step in sorted({r["first_positive_loss_step"] for r in rows if r["first_positive_loss_step"] is not None})
            },
            "repeated_tool_names":sum(r["repeated_tool_names"] for r in rows),
            "nonproductive_type_repeats":sum(r["nonproductive_type_repeats"] for r in rows),
        }
    return {
        "status":"verified_offline",
        "provider_calls":0,
        "base_tasks":5,
        "native_trajectories":30,
        "state_model":"actual successful native tool outputs, projected to accumulated typed-state; no hidden simulator reads",
        "step_loss_definition":"c(s,a)+V*(typed_state_after)-V*(typed_state_before)",
        "value_source":"independently reconstructed shortest feasible continuation over current native tool graph",
        "verified_telescoping":True,
        "per_policy":summary,
        "trajectories":output,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root",required=True,type=Path)
    parser.add_argument("--trajectories",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    raw=[json.loads(line) for line in args.trajectories.read_text(encoding="utf-8").splitlines() if line.strip()]
    checkpoints,_=confirmation.load_checkpoints(args.costbench_root.resolve())
    result=analyze(raw,checkpoints)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="trajectories"},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
