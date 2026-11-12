#!/usr/bin/env python3
"""Reproduce the offline AdaPlanner-trigger transfer audit from committed data."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json")
COHORT = Path("research/costbench_method_studies/plan_commitment_evidence_gate/evidence/native_event_cohort_67/RESULTS.json")
DYNAMIC = Path("research/costbench_method_studies/official_dev_baseline/evidence/results/official_cost_change")
OUT_JSON = Path("research/plan_commitment_pilot/evidence/ADAPLANNER_TRIGGER_TRANSFER_AUDIT.json")
OUT_CSV = Path("research/plan_commitment_pilot/evidence/ADAPLANNER_TRIGGER_TRANSFER_AUDIT.csv")
ERROR_MARKER = re.compile(
    r"^\s*\[(?:ERROR|RUNTIME ERROR|CODE ERROR)\]|"
    r"\[(?:ERROR|RUNTIME ERROR|CODE ERROR)\]|"
    r"(?:^|\n)\s*(?:ERROR|Error):|"
    r"\bmissing prerequisite\b|\btool\s+\S+\s+not found\b",
    re.IGNORECASE,
)
CSV_COLUMNS = [
    "query_id", "category", "event_step", "event_type", "event_change_trigger",
    "post_event_tool_output_count", "post_event_tool_error_count",
    "ada_execution_failure_proxy", "incumbent_feasible",
    "current_incumbent_value", "current_best_value", "objective_gap",
    "frozen_decision_margin", "graph_reference_trigger", "graph_reference_action",
    "actual_post_event_calls", "first_action", "first_action_follows_incumbent",
    "first_action_matches_current_optimum", "exact_incumbent_suffix",
    "exact_current_optimal_suffix", "goal_reached", "official_final_answer_accepted",
]


def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda _token: None,
    )


def normalize_query_id(value):
    return str(value).strip().strip("<>")


def build_audit(root: Path = ROOT):
    original = read_json(root / AUDIT)
    cohort = read_json(root / COHORT)
    cohort_by_id = {row["query_id"]: row for row in cohort["records"]}

    raw_by_id = {}
    source_files = []
    for shard in range(4):
        path = (
            root / DYNAMIC
            / f"shard{shard:02d}"
            / "results_deepseek-flash_blocked-cost_change-1_refinement_2.json"
        )
        source_files.append(path.relative_to(root).as_posix())
        for raw in read_json(path)["results"]:
            qid = normalize_query_id(raw["query_id"])
            if qid in raw_by_id:
                raise ValueError(f"duplicate raw task: {qid}")
            raw_by_id[qid] = raw
    if len(raw_by_id) != 80:
        raise ValueError(f"expected 80 official dynamic tasks, got {len(raw_by_id)}")

    records = []
    for audit_row in original["rows"]:
        qid = audit_row["query_id"]
        raw = raw_by_id.get(qid)
        cohort_row = cohort_by_id.get(qid)
        if raw is None or cohort_row is None:
            raise ValueError(f"missing source record: {qid}")
        if cohort_row.get("pre_event_text_plan_memory", {}).get("status") != "VALID_PRE_EVENT_COMMITMENT":
            raise ValueError(f"plan status mismatch: {qid}")

        stats = raw.get("block_stats") or {}
        block_types = stats.get("block_type") or []
        block_steps = stats.get("block_step") or []
        if len(block_types) != 1 or len(block_steps) != 1:
            raise ValueError(f"expected one event and one event step: {qid}")
        event_type = str(block_types[0])
        event_step = block_steps[0]
        if not isinstance(event_step, int) or event_step < 1:
            raise ValueError(f"invalid event step: {qid}")

        tool_outputs = [
            message.get("content") or ""
            for message in raw.get("conversation_history") or []
            if message.get("role") == "tool"
        ]
        post_event_outputs = tool_outputs[event_step:]
        errors = [message for message in post_event_outputs if ERROR_MARKER.search(message)]
        goal_reached = raw.get("is_goal_state") is True
        decision = cohort_row.get("counterfactual_decision_audit") or {}
        incumbent_value = decision.get("incumbent_updated_cost")
        best_value = decision.get("current_full_optimal_cost")
        if not isinstance(incumbent_value, (int, float)) or not math.isfinite(incumbent_value):
            raise ValueError(f"missing finite incumbent value: {qid}")
        if not isinstance(best_value, (int, float)) or not math.isfinite(best_value):
            raise ValueError(f"missing finite current-best value: {qid}")

        gap = round(float(incumbent_value) - float(best_value), 6)
        if gap < -1e-6:
            raise ValueError(f"negative incumbent gap: {qid} ({gap})")
        gap = max(0.0, gap)
        margin = float(decision.get("switch_penalty", 0.25))
        graph_switch = gap > margin + 1e-9
        graph_action = decision.get("action")
        if graph_switch != (graph_action == "SWITCH_FROM_OBSERVED_LLM_PLAN"):
            raise ValueError(f"graph reference action mismatch: {qid}")
        if audit_row.get("gate_action") != graph_action:
            raise ValueError(f"original audit action mismatch: {qid}")

        records.append({
            "query_id": qid,
            "category": audit_row["category"],
            "event_step": event_step,
            "event_type": event_type,
            "event_change_trigger": event_type == "cost_change",
            "post_event_tool_output_count": len(post_event_outputs),
            "post_event_tool_error_count": len(errors),
            "ada_execution_failure_proxy": bool(errors) or not goal_reached,
            "incumbent_suffix": audit_row["incumbent_suffix"],
            "incumbent_feasible": True,
            "current_incumbent_value": float(incumbent_value),
            "current_best_value": float(best_value),
            "objective_gap": gap,
            "frozen_decision_margin": margin,
            "graph_reference_trigger": graph_switch,
            "graph_reference_action": graph_action,
            "actual_post_event_calls": audit_row["actual_post_event_calls"],
            "first_action": audit_row["first_action"],
            "first_action_follows_incumbent": audit_row["first_action_follows_incumbent"],
            "first_action_matches_current_optimum": audit_row["first_action_matches_current_optimum"],
            "exact_incumbent_suffix": audit_row["exact_incumbent_suffix"],
            "exact_current_optimal_suffix": audit_row["exact_current_optimal_suffix"],
            "goal_reached": goal_reached,
            "official_final_answer_accepted": (raw.get("evaluation") or {}).get("success") is True,
        })

    records.sort(key=lambda row: row["query_id"])
    count = lambda predicate: sum(bool(predicate(row)) for row in records)
    event_counts = dict(sorted(Counter(row["event_type"] for row in records).items()))
    event_step_counts = dict(sorted(Counter(str(row["event_step"]) for row in records).items()))
    summary = {
        "official_development_tasks": 80,
        "observed_dynamic_event_tasks": 67,
        "valid_agent_authored_plan_tasks": len(records),
        "event_type_counts": event_counts,
        "event_step_counts": event_step_counts,
        "coarse_cost_change_triggered": count(lambda row: row["event_change_trigger"]),
        "ada_execution_failure_proxy_triggered": count(lambda row: row["ada_execution_failure_proxy"]),
        "incumbent_plan_feasible": count(lambda row: row["incumbent_feasible"]),
        "post_event_tool_error_outputs": sum(row["post_event_tool_error_count"] for row in records),
        "post_event_tool_outputs": sum(row["post_event_tool_output_count"] for row in records),
        "goal_reached": count(lambda row: row["goal_reached"]),
        "official_final_answer_accepted": count(lambda row: row["official_final_answer_accepted"]),
        "first_action_follows_incumbent": count(lambda row: row["first_action_follows_incumbent"]),
        "first_action_matches_current_optimum": count(lambda row: row["first_action_matches_current_optimum"]),
        "first_action_not_current_optimum": count(lambda row: not row["first_action_matches_current_optimum"]),
        "positive_objective_gap": count(lambda row: row["objective_gap"] > 1e-6),
        "zero_objective_gap": count(lambda row: row["objective_gap"] <= 1e-6),
        "positive_gap_within_frozen_margin": count(
            lambda row: 1e-6 < row["objective_gap"] <= row["frozen_decision_margin"] + 1e-9
        ),
        "gap_exceeds_frozen_margin": count(
            lambda row: row["objective_gap"] > row["frozen_decision_margin"] + 1e-9
        ),
        "graph_reference_retain": count(lambda row: not row["graph_reference_trigger"]),
        "graph_reference_switch": count(lambda row: row["graph_reference_trigger"]),
    }
    if summary["valid_agent_authored_plan_tasks"] != 27:
        raise ValueError("expected 27 valid Agent-authored plans")
    if summary["ada_execution_failure_proxy_triggered"] != 0:
        raise ValueError("unexpected failure-proxy trigger; inspect source outputs")
    if summary["graph_reference_switch"] != 5 or summary["graph_reference_retain"] != 22:
        raise ValueError("graph-reference split differs from frozen audit")

    return {
        "schema": "adaplanner-trigger-transfer-audit-v1",
        "status": "offline_development_audit",
        "provider_calls": 0,
        "scope": (
            "27 uniquely recoverable Agent-authored plans selected from 67 observed "
            "dynamic events in the official 80-task development population"
        ),
        "source_files": {
            "original_agent_audit": AUDIT.as_posix(),
            "native_event_cohort": COHORT.as_posix(),
            "original_dynamic_shards": source_files,
            "upstream_adaplanner_notebook": (
                "https://github.com/haotiansun14/AdaPlanner/blob/main/ALFWorld/alfworld.ipynb"
            ),
            "upstream_costbench_blocker": (
                "https://github.com/JiayuJeff/CostBench/blob/"
                "6424069f3f773ade076bcedbed302ed47cfb1837/env/utils/blocker.py"
            ),
            "upstream_costbench_tool_registry": (
                "https://github.com/JiayuJeff/CostBench/blob/"
                "6424069f3f773ade076bcedbed302ed47cfb1837/"
                "env/domains/travel/tool_registry.py"
            ),
        },
        "trigger_definitions": {
            "ada_execution_failure_proxy": (
                "A post-event native tool output contains a clear execution-error marker, "
                "or the task does not reach its native goal state. This is a cross-benchmark "
                "proxy, not a replay of AdaPlanner Python assertions."
            ),
            "coarse_environment_event": "Any recorded CostBench cost_change event.",
            "graph_reference_trigger": (
                "The independently audited incumbent-versus-current-best objective gap "
                "exceeds the pre-existing frozen decision margin for that task. This is "
                "retrospective graph evidence, not an LLM-only trigger."
            ),
        },
        "summary": summary,
        "interpretation_boundaries": [
            "CostBench does not log AdaPlanner-style generated Python assertions, predicted-observation assertions, or code checkpoints. The execution-failure proxy cannot be interpreted as an exact AdaPlanner replay.",
            "All selected cases are development tasks with uniquely recoverable Agent-authored plans; they are a subset of 27 out of 67 observed events, not a random held-out cohort.",
            "The 0.25 decision margin is inherited from the existing frozen evidence-gate protocol; it was not tuned on these outcomes.",
            "First-action mismatch with the selected graph-optimal first action is not identical to positive full-path objective gap because alternative optimal paths and downstream differences can occur.",
            "The graph-reference trigger uses an exact current public-tool graph audit. It is a diagnostic reference, not a validated AdaPlanner implementation.",
            "The benchmark event changes tool-cost attributes. It is used here as a controlled plan-relevant environment update, not as a claim that tool-cost optimization is the research contribution.",
        ],
        "records": records,
    }


def render_csv(data):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in data["records"]:
        encoded = dict(row)
        for field in ("incumbent_suffix", "actual_post_event_calls"):
            encoded[field] = " -> ".join(encoded[field])
        writer.writerow({key: encoded.get(key) for key in CSV_COLUMNS})
    return output.getvalue().replace("\r\n", "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build_audit()
    json_path = ROOT / OUT_JSON
    csv_path = ROOT / OUT_CSV
    json_text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    csv_text = render_csv(data)
    if args.check:
        if read_json(json_path) != data:
            raise SystemExit("committed trigger-audit JSON is stale")
        if csv_path.read_text(encoding="utf-8") != csv_text:
            raise SystemExit("committed trigger-audit CSV is stale")
        print("ADAPLANNER_TRIGGER_TRANSFER_AUDIT_OK", json.dumps(data["summary"], sort_keys=True))
    else:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json_text, encoding="utf-8")
        csv_path.write_text(csv_text, encoding="utf-8")
        print("ADAPLANNER_TRIGGER_TRANSFER_AUDIT_WRITTEN", json.dumps(data["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
