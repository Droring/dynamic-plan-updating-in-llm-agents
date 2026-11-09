#!/usr/bin/env python3
"""Audit original native Agent actions against recoverable pre-event plans.

Reads committed official CostBench dynamic-run outputs only. No model or
network calls are made.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GATE_AUDIT = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/NATIVE_AUDIT.json")
COHORT = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/native_event_cohort_67/RESULTS.json")
DYNAMIC_BASE = Path("research/costbench_method_studies/official_dev_baseline/evidence/results/official_cost_change")
OUT_JSON = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json")
OUT_CSV = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.csv")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: None)


def normalize_query_id(value):
    return str(value).strip().strip("<>")


def extract_tool_calls(history):
    calls = []
    for message in history or []:
        for call in message.get("tool_calls") or []:
            name = call.get("name") or (call.get("function") or {}).get("name")
            if not name:
                raise ValueError("tool call without function name")
            calls.append(name)
    return calls


def event_step(block_stats):
    steps = block_stats.get("block_step")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], int) or steps[0] < 1:
        raise ValueError(f"invalid event-step record: {steps!r}")
    if block_stats.get("block_count_agent") != 1 or block_stats.get("block_type") != ["cost_change"]:
        raise ValueError("expected exactly one official CostBench cost-change event")
    return steps[0]


def build_audit(root: Path = ROOT):
    gate_audit = read_json(root / GATE_AUDIT)
    cohort = read_json(root / COHORT)
    gate_by_id = {item["query_id"]: item for item in gate_audit["cases"]}
    cohort_records = {item["query_id"]: item for item in cohort["records"]}

    raw_by_id = {}
    source_files = []
    for shard in range(4):
        path = root / DYNAMIC_BASE / f"shard{shard:02d}" / "results_deepseek-flash_blocked-cost_change-1_refinement_2.json"
        source_files.append(path.relative_to(root).as_posix())
        for item in read_json(path)["results"]:
            qid = normalize_query_id(item["query_id"])
            if qid in raw_by_id:
                raise ValueError(f"duplicate original task: {qid}")
            raw_by_id[qid] = item
    if len(raw_by_id) != 80:
        raise ValueError(f"expected 80 official dynamic tasks, got {len(raw_by_id)}")

    valid = [
        item for item in cohort["records"]
        if item.get("pre_event_text_plan_memory", {}).get("status") == "VALID_PRE_EVENT_COMMITMENT"
    ]
    if len(valid) != 27:
        raise ValueError(f"expected 27 recoverable Agent-authored plans, got {len(valid)}")

    rows = []
    for item in sorted(valid, key=lambda x: x["query_id"]):
        qid = item["query_id"]
        raw, gate = raw_by_id.get(qid), gate_by_id.get(qid)
        if raw is None or gate is None:
            raise ValueError(f"missing original run or gate record: {qid}")
        memory = item["pre_event_text_plan_memory"]
        decision = item["counterfactual_decision_audit"]
        incumbent = memory["remaining_suffix"]
        optimal = decision["current_optimal_suffix"]
        full_plan = memory["full_path"]
        if gate.get("commitment_status") != "VALID_PRE_EVENT_COMMITMENT":
            raise ValueError(f"gate audit does not validate {qid}")
        if gate.get("model_written_remaining_suffix") != incumbent:
            raise ValueError(f"incumbent suffix mismatch for {qid}")
        if gate.get("gate_action") != decision.get("action"):
            raise ValueError(f"gate action mismatch for {qid}")

        step = event_step(raw.get("block_stats") or {})
        calls = extract_tool_calls(raw.get("conversation_history"))
        prefix, actual = calls[:step], calls[step:]
        if prefix != full_plan[:step]:
            raise ValueError(f"original pre-event prefix does not match written plan: {qid}")
        if not actual or not incumbent or not optimal:
            raise ValueError(f"missing post-event path or plan suffix: {qid}")

        first = actual[0]
        rows.append({
            "query_id": qid,
            "category": item["category"],
            "event_step": step,
            "gate_action": gate["gate_action"],
            "switch_penalty": decision.get("switch_penalty"),
            "incumbent_suffix": incumbent,
            "actual_post_event_calls": actual,
            "current_optimal_suffix": optimal,
            "pre_event_prefix_matches_agent_plan": True,
            "first_action": first,
            "incumbent_first_action": incumbent[0],
            "optimal_first_action": optimal[0],
            "first_action_follows_incumbent": first == incumbent[0],
            "first_action_matches_current_optimum": first == optimal[0],
            "exact_incumbent_suffix": actual == incumbent,
            "exact_current_optimal_suffix": actual == optimal,
            "goal_reached": raw.get("is_goal_state") is True,
            "official_final_answer_accepted": (raw.get("evaluation") or {}).get("success") is True,
            "actual_post_event_call_count": len(actual),
        })

    gate_counts = Counter(row["gate_action"] for row in rows)
    retain = [row for row in rows if row["gate_action"] == "RETAIN_OBSERVED_LLM_PLAN"]
    switch = [row for row in rows if row["gate_action"] == "SWITCH_FROM_OBSERVED_LLM_PLAN"]

    def n(items, field):
        return sum(bool(row[field]) for row in items)

    summary = {
        "official_development_tasks": 80,
        "observed_dynamic_event_tasks": 67,
        "valid_agent_authored_plan_tasks": len(rows),
        "gate_action_counts": dict(sorted(gate_counts.items())),
        "original_agent_behavior": {
            "pre_event_prefix_matches_agent_plan": n(rows, "pre_event_prefix_matches_agent_plan"),
            "first_action_follows_incumbent": n(rows, "first_action_follows_incumbent"),
            "first_action_matches_current_optimum": n(rows, "first_action_matches_current_optimum"),
            "first_action_not_current_optimum": len(rows) - n(rows, "first_action_matches_current_optimum"),
            "exact_incumbent_suffix": n(rows, "exact_incumbent_suffix"),
            "exact_current_optimal_suffix": n(rows, "exact_current_optimal_suffix"),
            "goal_reached": n(rows, "goal_reached"),
            "official_final_answer_accepted": n(rows, "official_final_answer_accepted"),
        },
        "gate_retain_subset": {
            "n": len(retain),
            "first_action_follows_incumbent": n(retain, "first_action_follows_incumbent"),
            "first_action_matches_current_optimum": n(retain, "first_action_matches_current_optimum"),
            "exact_incumbent_suffix": n(retain, "exact_incumbent_suffix"),
            "exact_current_optimal_suffix": n(retain, "exact_current_optimal_suffix"),
        },
        "gate_switch_subset": {
            "n": len(switch),
            "first_action_follows_incumbent": n(switch, "first_action_follows_incumbent"),
            "first_action_matches_current_optimum": n(switch, "first_action_matches_current_optimum"),
            "exact_incumbent_suffix": n(switch, "exact_incumbent_suffix"),
            "exact_current_optimal_suffix": n(switch, "exact_current_optimal_suffix"),
            "false_retain_first_actions": n(switch, "first_action_follows_incumbent"),
        },
    }
    return {
        "schema": "original-native-agent-retention-audit",
        "source_files": {
            "official_dynamic_shards": source_files,
            "gate_audit": GATE_AUDIT.as_posix(),
            "native_event_cohort": COHORT.as_posix(),
        },
        "summary": summary,
        "interpretation_boundary": [
            "The 27 cases are the selected subset of 67 observed dynamic events where an Agent-authored pre-event plan was uniquely recoverable.",
            "Actual post-event actions are extracted from original official CostBench conversation_history, not from deterministic evidence-gate replay.",
            "The 22/5 RETAIN/SWITCH counts are deterministic gate actions using the recorded 0.25 switch penalty; they are not model labels.",
            "The current-optimal suffix comes from the independent current-checkpoint graph audit.",
            "All 27 original trajectories reached the goal, but goal completion does not establish that the first post-event action was the best current continuation.",
            "This is a selected development subset and does not establish generalization to held-out tasks or reveal hidden model reasoning.",
        ],
        "rows": rows,
    }


def render_csv(data):
    columns = [
        "query_id", "category", "event_step", "gate_action", "switch_penalty",
        "incumbent_suffix", "actual_post_event_calls", "current_optimal_suffix",
        "pre_event_prefix_matches_agent_plan", "first_action", "incumbent_first_action",
        "optimal_first_action", "first_action_follows_incumbent",
        "first_action_matches_current_optimum", "exact_incumbent_suffix",
        "exact_current_optimal_suffix", "goal_reached",
        "official_final_answer_accepted", "actual_post_event_call_count",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in data["rows"]:
        encoded = dict(row)
        for field in ("incumbent_suffix", "actual_post_event_calls", "current_optimal_suffix"):
            encoded[field] = " -> ".join(encoded[field])
        writer.writerow(encoded)
    return buffer.getvalue()


def write_outputs(data):
    (ROOT / OUT_JSON).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (ROOT / OUT_CSV).write_text(render_csv(data), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify committed JSON and CSV outputs")
    args = parser.parse_args()
    data = build_audit()
    if args.check:
        if read_json(ROOT / OUT_JSON) != data:
            raise SystemExit("committed original-agent audit JSON is stale")
        if (ROOT / OUT_CSV).read_text(encoding="utf-8") != render_csv(data):
            raise SystemExit("committed original-agent audit CSV is stale")
        print("ORIGINAL_AGENT_RETENTION_AUDIT_OK", json.dumps(data["summary"], sort_keys=True))
    else:
        write_outputs(data)
        print("ORIGINAL_AGENT_RETENTION_AUDIT_WRITTEN", json.dumps(data["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
