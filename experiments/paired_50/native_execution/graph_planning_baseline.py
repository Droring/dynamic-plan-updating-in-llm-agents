#!/usr/bin/env python3
"""Information-matched graph-planning baseline for frozen CostBench checkpoints.

No GroundtruthSolver or model calls in the policy. This is a strong baseline,
not a proposed new LLM algorithm. Reconstructs the same typed tool graph used
by the bounded candidate verifier, without the LLM candidate restriction.
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import json
import os
from pathlib import Path

import run_bounded_verifier_confirmation as confirmation
import bounded_candidate_verifier as bounded

HERE = Path(__file__).resolve().parent


def shortest_feasible_path(prepared, max_steps=None, expansion_limit=200000):
    """Graph Dijkstra from current typed state to goal; nonnegative action weights."""
    state = frozenset(prepared["state"])
    goal = prepared["goal_type"]
    if goal in state:
        return 0.0, []
    count = itertools.count()
    heap = [(0.0, 0, next(count), state, ())]
    best = {(state, 0) if max_steps is not None else state: 0.0}
    visited = 0
    while heap:
        value, steps, _, available, path = heapq.heappop(heap)
        key = (available, steps) if max_steps is not None else available
        if value > best.get(key, float("inf")) + 1e-9:
            continue
        visited += 1
        if visited > expansion_limit:
            raise RuntimeError("Graph search expansion ceiling exceeded")
        if goal in available:
            return value, list(path)
        if max_steps is not None and steps >= max_steps:
            continue
        for name, tool in prepared["tool_objects"].items():
            if float(tool.cost) < 0:
                raise ValueError("Dijkstra requires nonnegative weights")
            if tool.output_type in available or not set(tool.input_types).issubset(available):
                continue
            new_state = available.union([tool.output_type])
            new_value = value + float(tool.cost)
            next_key = (new_state, steps + 1) if max_steps is not None else new_state
            if new_value + 1e-9 >= best.get(next_key, float("inf")):
                continue
            best[next_key] = new_value
            heapq.heappush(heap, (new_value, steps+1, next(count),
                                  new_state, path + (name,)))
    return None


def compare(checkpoints):
    rows = []
    for trial in checkpoints:
        prepared = trial["prepared"]
        full = shortest_feasible_path(prepared)
        four = shortest_feasible_path(prepared, max_steps=4)
        incumbent = bounded.incumbent_path_value(prepared, prepared["incumbent_suffix"])
        if full is None or incumbent is None:
            raise ValueError("Frozen checkpoint is not solvable")
        rows.append({
            "query_id": trial["query_id"],
            "environment": trial["environment_condition"],
            "full_shortest_path": full[1],
            "full_shortest_value": full[0],
            "bounded_four_step_path": four[1] if four else None,
            "bounded_four_step_value": four[0] if four else None,
            "incumbent_path": prepared["incumbent_suffix"],
            "incumbent_value": incumbent,
            "full_improves_incumbent": full[0] < incumbent - 1e-6,
            "four_step_improves_incumbent": bool(four and four[0] < incumbent - 1e-6),
            "same_first_action_as_incumbent": full[1][0] == prepared["incumbent_suffix"][0],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.costbench_root.resolve()
    trials, _cb = confirmation.load_checkpoints(root)
    rows = compare(trials)
    by_condition = {}
    for condition in ("RETAIN", "SWITCH"):
        subset = [r for r in rows if r["environment"] == condition]
        by_condition[condition] = {
            "tasks": len(subset),
            "full_path_improves_incumbent": sum(r["full_improves_incumbent"] for r in subset),
            "four_step_path_improves_incumbent": sum(r["four_step_improves_incumbent"] for r in subset),
            "full_first_action_follows_incumbent": sum(r["same_first_action_as_incumbent"] for r in subset),
            "full_path_reaches_goal_in_type_graph": len(subset),
        }
    output = {
        "status": "offline_graph_baseline_complete",
        "policy_oracle_calls": 0,
        "policy_model_calls": 0,
        "reference_solver_used": False,
        "matching_information_access": "Current native typed state, tool inputs, outputs and visible values",
        "task_count": 10, "checkpoint_count": 20,
        "by_condition": by_condition,
        "note": "These are graph-reachable paths, not yet executed through native tool interfaces.",
        "rows": rows,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in output.items() if k!="rows"}, indent=2))


if __name__ == "__main__":
    main()
