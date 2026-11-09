#!/usr/bin/env python3
"""Offline stratification of SWITCH failures by the location of the changed tool.

Uses only the frozen 100 requests, archived native traces and independent
trajectory-value audit. No model/provider calls are made.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

TOL = 1e-6


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def request_sha(value):
    import hashlib
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def classify_changed_tool(changed_tool: str, incumbent: list[str], delta: float) -> str:
    inside = changed_tool in incumbent
    if inside and delta > TOL:
        return "incumbent_tool_increased"
    if not inside and delta < -TOL:
        return "outside_alternative_decreased"
    if inside:
        return "incumbent_tool_other_change"
    return "outside_tool_other_change"


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["change_pattern"]].append(row)
    out = {}
    for name, items in sorted(groups.items()):
        out[name] = {
            "n": len(items),
            "first_action_followed_incumbent": sum(x["first_action_followed_incumbent"] for x in items),
            "exact_incumbent_suffix": sum(x["exact_incumbent_suffix"] for x in items),
            "alternative_continuation": sum(not x["exact_incumbent_suffix"] for x in items),
            "value_optimal": sum(x["value_optimal"] for x in items),
            "nonoptimal": sum(not x["value_optimal"] for x in items),
            "query_ids": sorted(x["query_id"] for x in items),
            "optimal_query_ids": sorted(x["query_id"] for x in items if x["value_optimal"]),
        }
    return out


def run(responses_path: Path, requests_path: Path, trajectory_audit_path: Path, out_dir: Path):
    responses = read_jsonl(responses_path)
    requests = read_jsonl(requests_path)
    if len(responses) != 100 or len(requests) != 100:
        raise ValueError("expected exactly 100 native responses and 100 frozen requests")

    request_by_trial = {x["trial_id"]: x for x in requests}
    if len(request_by_trial) != 100:
        raise ValueError("duplicate frozen trial IDs")
    response_by_pair = defaultdict(dict)
    for response in responses:
        trial_id = response["trial_id"]
        request = request_by_trial[trial_id]
        if response["request_sha256"] != request_sha(request):
            raise ValueError(f"request hash mismatch: {trial_id}")
        if response["checkpoint_sha256"] != request["checkpoint_sha256"]:
            raise ValueError(f"checkpoint hash mismatch: {trial_id}")
        if response["condition"] in response_by_pair[response["query_id"]]:
            raise ValueError(f"duplicate paired condition: {trial_id}")
        response_by_pair[response["query_id"]][response["condition"]] = response

    with trajectory_audit_path.open("r", newline="", encoding="utf-8") as handle:
        audit_rows = list(csv.DictReader(handle))
    audit_by_pair = {(x["query_id"], x["condition"]): x for x in audit_rows}
    if len(audit_by_pair) != 100:
        raise ValueError("trajectory audit must contain 100 unique query-condition rows")

    rows = []
    pair_validation = {
        "paired_tasks": 0,
        "same_checkpoint": True,
        "same_incumbent_suffix": True,
        "changed_tool_consistent": True,
        "only_changed_tool_value_differs": True,
    }
    for query_id, arms in sorted(response_by_pair.items()):
        if set(arms) != {"RETAIN", "SWITCH"}:
            raise ValueError(f"incomplete pair: {query_id}")
        retain = arms["RETAIN"]
        switch = arms["SWITCH"]
        retain_request = request_by_trial[retain["trial_id"]]
        switch_request = request_by_trial[switch["trial_id"]]
        retain_visible = json.loads(retain_request["messages"][-1]["content"])
        switch_visible = json.loads(switch_request["messages"][-1]["content"])

        incumbent = retain_visible["supplied_old_plan_suffix"]
        if incumbent != switch_visible["supplied_old_plan_suffix"]:
            pair_validation["same_incumbent_suffix"] = False
            raise ValueError(f"incumbent suffix mismatch: {query_id}")
        if retain["checkpoint_sha256"] != switch["checkpoint_sha256"]:
            pair_validation["same_checkpoint"] = False
            raise ValueError(f"checkpoint mismatch: {query_id}")
        if retain["changed_tool"] != switch["changed_tool"]:
            pair_validation["changed_tool_consistent"] = False
            raise ValueError(f"changed tool mismatch: {query_id}")

        changed_tool = switch["changed_tool"]
        retain_tools = retain_visible["current_tools"]
        switch_tools = switch_visible["current_tools"]
        if set(retain_tools) != set(switch_tools) or changed_tool not in switch_tools:
            raise ValueError(f"tool registry mismatch: {query_id}")

        changed_costs = []
        for name in sorted(retain_tools):
            a, b = retain_tools[name], switch_tools[name]
            if a["input_types"] != b["input_types"] or a["output_type"] != b["output_type"]:
                pair_validation["only_changed_tool_value_differs"] = False
                raise ValueError(f"tool schema changed across pair: {query_id}/{name}")
            delta_i = float(b["cost"]) - float(a["cost"])
            if abs(delta_i) > TOL:
                changed_costs.append(name)
        if changed_costs != [changed_tool]:
            pair_validation["only_changed_tool_value_differs"] = False
            raise ValueError(f"expected only {changed_tool} value to change, got {changed_costs}")

        delta = float(switch_tools[changed_tool]["cost"]) - float(retain_tools[changed_tool]["cost"])
        pattern = classify_changed_tool(changed_tool, incumbent, delta)
        audit = audit_by_pair[(query_id, "SWITCH")]
        first_action = switch["first_action"]
        executed_path = switch["executed_path"]
        optimal = as_bool(audit["value_optimal"])
        row = {
            "query_id": query_id,
            "changed_tool": changed_tool,
            "change_pattern": pattern,
            "changed_tool_in_incumbent": changed_tool in incumbent,
            "incumbent_suffix": " -> ".join(incumbent),
            "retain_tool_value": float(retain_tools[changed_tool]["cost"]),
            "switch_tool_value": float(switch_tools[changed_tool]["cost"]),
            "tool_value_delta": delta,
            "first_action": first_action,
            "incumbent_first_action": incumbent[0],
            "first_action_followed_incumbent": first_action == incumbent[0],
            "executed_path": " -> ".join(executed_path),
            "exact_incumbent_suffix": executed_path == incumbent,
            "path_regret": float(audit["path_regret"]),
            "first_action_regret": float(audit["first_action_regret"]),
            "later_action_regret": float(audit["later_action_regret"]),
            "value_optimal": optimal,
            "goal_reached": as_bool(audit["goal_reached"]),
        }
        rows.append(row)
        pair_validation["paired_tasks"] += 1

    if len(rows) != 50:
        raise ValueError(f"expected 50 SWITCH strata rows, got {len(rows)}")
    if not all(pair_validation[k] for k in (
        "same_checkpoint", "same_incumbent_suffix", "changed_tool_consistent",
        "only_changed_tool_value_differs"
    )):
        raise ValueError("paired fixture validation failed")

    summary = {
        "schema": "paired-50-native-switch-mechanism-strata-v1",
        "independent_base_tasks": 50,
        "switch_conditions": 50,
        "pair_validation": pair_validation,
        "strata": summarize(rows),
        "overall": {
            "first_action_followed_incumbent": sum(x["first_action_followed_incumbent"] for x in rows),
            "exact_incumbent_suffix": sum(x["exact_incumbent_suffix"] for x in rows),
            "value_optimal": sum(x["value_optimal"] for x in rows),
            "nonoptimal": sum(not x["value_optimal"] for x in rows),
            "optimal_query_ids": sorted(x["query_id"] for x in rows if x["value_optimal"]),
        },
        "interpretation_boundary": [
            "This is a post-hoc descriptive split of the frozen paired cohort, not a randomized causal test.",
            "The incumbent suffix in this cohort is solver-derived and supplied at the checkpoint; this does not establish an Agent-authored plan-commitment effect.",
            "Changed-tool location and value direction describe the fixture construction; they do not identify the model's internal reason for selecting an action.",
            "All 50 paired task units are counted once; the 50 SWITCH rows are not treated as 50 additional independent tasks beyond the paired cohort.",
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=False)
    with (out_dir / "switch_strata.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--trajectory-audit", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.responses, args.requests, args.trajectory_audit, args.out_dir)
