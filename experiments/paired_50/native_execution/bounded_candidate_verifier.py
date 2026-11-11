#!/usr/bin/env python3
"""Bounded evidence verification for two LLM-proposed first actions.

This is a *classical graph-verification baseline*, not a new learned LLM
algorithm. The deployed gate does not call the CostBench GroundtruthSolver.
It tests whether an alternate C-arm candidate has a verifiable, strictly
better continuation than the feasible incumbent suffix within four steps.
The official solver is consulted only for POST-HOC scoring.
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import json
from pathlib import Path

import run_counterfactual_gate as archived
import run_four_arm_experiment as benchmark

HERE = Path(__file__).resolve().parent
MAX_STEPS = 4
EPS = 1e-6
MAX_EXPANSIONS = 30000


def incumbent_path_value(prepared, path):
    """Exact objective value of the proposed *existing* tool sequence."""
    state = set(prepared["state"])
    goal = prepared["goal_type"]
    total = 0.0
    for name in path:
        tool = prepared["tool_objects"].get(name)
        if tool is None or not set(tool.input_types).issubset(state):
            return None
        total += float(tool.cost)
        state.add(tool.output_type)
    return total if goal in state else None


def candidate_completion(prepared, first_action, max_steps=MAX_STEPS):
    """Bounded state-space search from a specified first action; no oracle calls.

    The candidate first action is fixed externally. Search explores *only*
    feasible native tool transitions under current tool values and type state.
    Returns one certified complete path (value, names), or None.
    """
    state = frozenset(prepared["state"])
    goal = prepared["goal_type"]
    tools = prepared["tool_objects"]
    first = tools.get(first_action)
    if first is None or not set(first.input_types).issubset(state):
        return None
    start = state.union([first.output_type])
    if goal in start:
        return float(first.cost), [first_action]
    counter = itertools.count()
    initial = float(first.cost)
    heap = [(initial, 1, next(counter), start, (first_action,))]
    seen = {(start, 1): initial}
    expansions = 0
    while heap:
        value, steps, _, available, path = heapq.heappop(heap)
        if value > seen.get((available, steps), float("inf")) + EPS:
            continue
        expansions += 1
        if expansions > MAX_EXPANSIONS:
            return None
        if goal in available:
            return value, list(path)
        if steps >= max_steps:
            continue
        for name, tool in tools.items():
            if tool.output_type in available:
                continue
            if not set(tool.input_types).issubset(available):
                continue
            next_available = available.union([tool.output_type])
            next_steps = steps + 1
            next_value = value + float(tool.cost)
            key = (next_available, next_steps)
            if next_value + EPS >= seen.get(key, float("inf")):
                continue
            seen[key] = next_value
            heapq.heappush(heap, (next_value, next_steps,
                                  next(counter), next_available, path + (name,)))
    return None


def verify(prepared, incumbent, candidate):
    """Returns a certificate without accessing gold labels or oracle scores."""
    old_path = prepared["incumbent_suffix"]
    if old_path[0] != incumbent:
        raise ValueError("Incumbent is inconsistent with frozen original path")
    old_value = incumbent_path_value(prepared, old_path)
    if old_value is None:
        raise ValueError("Current incumbent suffix is not a feasible complete path")
    if candidate == incumbent:
        return {"decision": "KEEP", "incumbent_path_value": old_value,
                "candidate_path_value": None, "certified_candidate_path": None}
    alternative = candidate_completion(prepared, candidate)
    new_value = alternative[0] if alternative else None
    accept = new_value is not None and new_value < old_value - EPS
    return {
        "decision": "ACCEPT" if accept else "KEEP",
        "incumbent_path_value": round(old_value, 9),
        "candidate_path_value": round(new_value, 9) if new_value is not None else None,
        "certified_candidate_path": alternative[1] if alternative else None,
        "max_search_steps": MAX_STEPS,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--costbench-root", required=True, type=Path)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "bounded_verifier_audit.json")
    args = ap.parse_args()
    data = (HERE.parent / "generated").resolve()
    rows, indexed, _ = archived.prepare(args.archive.resolve(), args.costbench_root.resolve(), data)
    results = []
    for row in rows:
        prepared = indexed[(row["query_id"], row["environment"])][1]
        certificate = verify(prepared, row["incumbent"], row["candidate"])
        chosen = row["candidate"] if certificate["decision"] == "ACCEPT" else row["incumbent"]
        # Official native solver is used for evaluation only after selection.
        _, values, optimal = benchmark.optimal_first_actions(prepared)
        if chosen not in values:
            raise ValueError("Policy selected infeasible first action")
        results.append({
            "query_id": row["query_id"], "environment": row["environment"],
            "repetition": row["repetition"], "incumbent": row["incumbent"],
            "candidate": row["candidate"], "selected": chosen,
            "selected_optimal": chosen in optimal,
            "incumbent_optimal": row["incumbent"] in optimal,
            "candidate_optimal": row["candidate"] in optimal,
            "certificate": certificate,
        })
    def aggregate(env):
        subset = [x for x in results if x["environment"] == env]
        return {
            "total": len(subset),
            "correct_first_actions": sum(x["selected_optimal"] for x in subset),
            "accepted": sum(x["certificate"]["decision"] == "ACCEPT" for x in subset),
            "false_switches": sum(x["certificate"]["decision"] == "ACCEPT"
                                  and not x["selected_optimal"] for x in subset),
        }
    ret, switch = aggregate("RETAIN"), aggregate("SWITCH")
    result = {
        "status": "completed_offline_no_provider_calls",
        "policy": "bounded-candidate-certificate",
        "candidate_source": "archived plan-omitted C first tool actions",
        "independent_base_tasks": 8,
        "archived_first_action_trials": 32,
        "new_deepseek_calls": 0,
        "max_search_steps": MAX_STEPS,
        "oracle_used_by_policy": False,
        "native_solver_used_for_posthoc_score": True,
        "RETAIN": ret, "SWITCH": switch,
        "balanced_accuracy": 0.5 * (
            ret["correct_first_actions"] / ret["total"] +
            switch["correct_first_actions"] / switch["total"]
        ),
        "records": results,
    }
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "records"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
