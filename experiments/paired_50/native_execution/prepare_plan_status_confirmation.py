#!/usr/bin/env python3
"""Freeze a checkpoint-level two-arm plan-status annotation confirmation; offline only."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "generated"
sys.path.insert(0, str(HERE))

import graph_planning_baseline as graph
import run_official_harness as native

TOL = 1e-6
REPETITIONS = 2
ARMS = ("UNMARKED", "ANNOTATED")
ENVIRONMENTS = ("RETAIN", "SWITCH")
TASKS_PER_CATEGORY = 2
CATEGORIES = ("accommodation", "attraction", "dining", "shopping", "transportation")
PREVIOUS_HANDOFF_TASKS = {
    "Query00178", "Query00351", "Query00549", "Query00689", "Query00851"
}


def path_value(prepared: dict, state, path):
    """Return the native typed-graph value of a feasible path from a supplied state."""
    available = set(state)
    total = 0.0
    for name in path:
        tool = prepared["tool_objects"].get(name)
        if tool is None or not set(tool.input_types).issubset(available):
            return None
        if tool.output_type in available:
            return None
        total += float(tool.cost)
        available.add(tool.output_type)
    return total if prepared["goal_type"] in available else None


def classify_prior_status(incumbent_value, optimal_value):
    gap = float(incumbent_value) - float(optimal_value)
    if gap < -TOL:
        raise ValueError(f"Incumbent appears cheaper than independently computed optimum: {gap}")
    return ("VALID", max(0.0, gap)) if gap <= TOL else ("STALE", gap)


def make_status_message(incumbent_plan, replacement_path, goal, status):
    if status not in {"VALID", "STALE", "UNSET"}:
        raise ValueError(f"Unexpected prior-plan status: {status}")
    return (
        "[Planner-provided continuation]\n"
        "An external graph planner computed the following complete feasible minimum-cost "
        "continuation from the current checkpoint. It is supplied as a plan reference; "
        "use the current tool definitions and observations when executing it.\n"
        "Planner continuation: " + " -> ".join(replacement_path) + "\n\n"
        "[Previously supplied plan]\n"
        "Remaining incumbent suffix: " + " -> ".join(incumbent_plan) + "\n"
        "Status convention: VALID means this remaining incumbent suffix is still minimum-cost "
        "from the current checkpoint; STALE means it remains feasible but is strictly more "
        "expensive than a minimum-cost continuation; UNSET means no validity annotation "
        "is supplied. The status applies only to the remaining incumbent suffix.\n"
        "Prior-plan status: " + status + "."
    )


def previous_task_exclusions():
    four_arm = json.loads((HERE / "FOUR_ARM_TASK_MANIFEST.json").read_text(encoding="utf-8"))
    bounded = json.loads((HERE / "BOUNDED_VERIFIER_CONFIRMATION_MANIFEST.json").read_text(encoding="utf-8"))
    excluded = set(PREVIOUS_HANDOFF_TASKS)
    excluded.update(row["query_id"] for row in four_arm["tasks"])
    excluded.update(row["query_id"] for row in bounded["tasks"])
    return excluded


def reconstruct_all(costbench_root: Path):
    # CostBench native tool objects resolve travel configuration relative to this checkout.
    os.chdir(costbench_root)
    requests, source_manifest, registry = native.load_frozen_inputs(DATA_DIR)
    request_by_id = {row["trial_id"]: row for row in requests}
    registry_by_query = {row["task_id"]: row for row in registry["selection"]["task_ids"]}
    query_path = costbench_root / "env" / "data" / "runtime" / "queries" / "queries.json"
    query_rows = json.loads(query_path.read_text(encoding="utf-8"))
    queries = {row["query_id"].strip("<>"): row for row in query_rows}
    cb = native.load_costbench(costbench_root)
    prepared = {}
    for task_id, registry_row in registry_by_query.items():
        entries = [row for row in requests if row["query_id"] == task_id]
        if len(entries) != 2:
            raise ValueError(f"Expected paired frozen requests for {task_id}")
        for request in entries:
            source = source_manifest[request["trial_id"]]
            trial = native.prepare_trial(
                request, source, queries[task_id], registry_row, cb
            )
            if trial["checkpoint_sha256"] != registry_row["checkpoint_sha256"]:
                raise ValueError(f"Reconstructed checkpoint mismatch for {task_id}")
            prepared[(task_id, source["condition"])] = {
                "request": request,
                "source": source,
                "prepared": trial,
                "category": registry_row["category"],
            }
    if len(prepared) != 100:
        raise ValueError(f"Expected 100 reconstructed native checkpoints, found {len(prepared)}")
    return requests, source_manifest, registry, request_by_id, prepared, cb


def inspect_candidate(task_id, category, prepared):
    pair = {}
    for env in ENVIRONMENTS:
        item = prepared[(task_id, env)]
        p = item["prepared"]
        optimum = graph.shortest_feasible_path(p)
        incumbent_value = path_value(p, p["state"], p["incumbent_suffix"])
        if optimum is None or not optimum[1]:
            return None, f"no_nonempty_optimal_continuation:{env}"
        if incumbent_value is None:
            return None, f"incumbent_suffix_infeasible:{env}"
        status, gap = classify_prior_status(incumbent_value, optimum[0])
        expected = "VALID" if env == "RETAIN" else "STALE"
        if status != expected:
            return None, f"checkpoint_plan_status_mismatch:{env}:{status}"
        if abs(float(p["native_regret_audit"]) - gap) > TOL:
            raise ValueError(f"Independent graph value disagrees with native oracle audit: {task_id}/{env}")
        pair[env] = {
            "query_id": task_id,
            "category": category,
            "environment": env,
            "checkpoint_sha256": p["checkpoint_sha256"],
            "prefix": p["prefix"],
            "incumbent_plan": list(p["incumbent_suffix"]),
            "incumbent_value": round(float(incumbent_value), 8),
            "prior_plan_status": status,
            "status_gap": round(float(gap), 8),
            "replacement_plan": list(optimum[1]),
            "optimal_value": round(float(optimum[0]), 8),
            "changed_tool": p["changed_tool"],
            "changed_tool_position": (
                p["incumbent_suffix"].index(p["changed_tool"]) + 1
                if p["changed_tool"] in p["incumbent_suffix"] else "outside_incumbent"
            ),
            "tool_schema_sha256": native.canonical_sha(p["tool_interfaces"]),
            "source_trial_id": item["source"]["trial_id"],
        }

    retain = pair["RETAIN"]
    switch = pair["SWITCH"]
    for field in ("checkpoint_sha256", "prefix", "incumbent_plan"):
        if retain[field] != switch[field]:
            raise ValueError(f"Paired checkpoint {field} mismatch: {task_id}")
    if retain["prior_plan_status"] != "VALID" or switch["prior_plan_status"] != "STALE":
        raise ValueError(f"Paired plan-status contrast missing: {task_id}")
    return pair, None


def select_tasks(candidates):
    by_category = defaultdict(list)
    for row in candidates:
        by_category[row["category"]].append(row)
    selected = []
    for category in CATEGORIES:
        selected.extend(sorted(by_category[category], key=lambda x: x["query_id"])[:TASKS_PER_CATEGORY])
    counts = defaultdict(int)
    for row in selected:
        counts[row["category"]] += 1
    if len(selected) != 10 or any(counts[c] != TASKS_PER_CATEGORY for c in CATEGORIES):
        detail = {k: len(v) for k, v in by_category.items()}
        raise ValueError(f"Fewer than two eligible tasks in one or more categories; eligible={detail}")
    return selected


def build_requests(selected, prepared, official_run, repetitions=REPETITIONS):
    requests = []
    prompt_audit = []
    for task in selected:
        qid = task["query_id"]
        for env in ENVIRONMENTS:
            cell = task["cells"][env]
            p = prepared[(qid, env)]["prepared"]
            base_messages = [
                {"role": "system", "content": native.make_official_system_prompt(official_run, p["task"])},
                {"role": "user", "content": native.make_checkpoint_user_message(p)},
            ]
            prompts = {}
            for arm in ARMS:
                label = cell["prior_plan_status"] if arm == "ANNOTATED" else "UNSET"
                status_message = make_status_message(
                    cell["incumbent_plan"], cell["replacement_plan"], p["goal_type"], label
                )
                messages = copy.deepcopy(base_messages)
                messages.append({"role": "user", "content": status_message})
                payload = {
                    "model": native.MODEL,
                    "messages": messages,
                    "tools": p["tool_interfaces"],
                    "temperature": 0,
                    "max_tokens": 2048,
                    "tool_choice": "required",
                    "parallel_tool_calls": False,
                    "extra_body": {"thinking": {"type": "disabled"}},
                }
                prompts[arm] = {
                    "messages": messages,
                    "payload": payload,
                    "payload_sha256": native.canonical_sha(payload),
                }
            if prompts["UNMARKED"]["messages"][:-1] != prompts["ANNOTATED"]["messages"][:-1]:
                raise ValueError(f"Checkpoint history differs across status arms: {qid}/{env}")
            unmarked_text = prompts["UNMARKED"]["messages"][-1]["content"]
            annotated_text = prompts["ANNOTATED"]["messages"][-1]["content"]
            unmarked_normalized = unmarked_text.replace("Prior-plan status: UNSET.", "<STATUS>")
            annotated_normalized = annotated_text.replace(
                f"Prior-plan status: {cell['prior_plan_status']}.", "<STATUS>"
            )
            if unmarked_normalized != annotated_normalized:
                raise ValueError(f"Status arms differ outside the single status label: {qid}/{env}")
            prompt_audit.append({
                "query_id": qid,
                "environment": env,
                "same_checkpoint_history": True,
                "same_tool_schema": True,
                "same_replacement_plan": True,
                "status_only_difference": True,
                "unmarked_payload_sha256": prompts["UNMARKED"]["payload_sha256"],
                "annotated_payload_sha256": prompts["ANNOTATED"]["payload_sha256"],
            })
            for arm in ARMS:
                for repetition in range(1, repetitions + 1):
                    requests.append({
                        "trial_id": f"{qid}_{env}_{arm}_r{repetition}",
                        "query_id": qid,
                        "category": task["category"],
                        "environment": env,
                        "arm": "B",
                        "status_arm": arm,
                        "status_annotation": cell["prior_plan_status"] if arm == "ANNOTATED" else "UNSET",
                        "repetition": repetition,
                        "checkpoint_sha256": cell["checkpoint_sha256"],
                        "incumbent_plan": cell["incumbent_plan"],
                        "updated_plan": cell["replacement_plan"],
                        "payload": prompts[arm]["payload"],
                        "payload_sha256": prompts[arm]["payload_sha256"],
                        "reservation_units": native.reservation_for_call(
                            prompts[arm]["payload"]["messages"],
                            prompts[arm]["payload"]["tools"], 2048,
                        ),
                        "source_trial_id": cell["source_trial_id"],
                        "prior_plan_status_oracle": cell["prior_plan_status"],
                        "status_gap": cell["status_gap"],
                        "changed_tool": cell["changed_tool"],
                    })
    expected = len(selected) * len(ENVIRONMENTS) * len(ARMS) * repetitions
    if len(requests) != expected:
        raise ValueError(f"Expected {expected} requests, got {len(requests)}")
    return requests, prompt_audit


def prepare(costbench_root, out_dir, frozen_manifest=None):
    requests, source_manifest, registry, request_by_id, prepared, cb = reconstruct_all(costbench_root)
    excluded = previous_task_exclusions()
    categories = {row["task_id"]: row["category"] for row in registry["selection"]["task_ids"]}
    eligible = []
    rejected = defaultdict(int)
    for qid in sorted(categories):
        if qid in excluded:
            rejected["previously_used_mechanism_task"] += 1
            continue
        cells, reason = inspect_candidate(qid, categories[qid], prepared)
        if reason:
            rejected[reason] += 1
            continue
        eligible.append({"query_id": qid, "category": categories[qid], "cells": cells})

    diagnostic = {
        "eligible_task_ids_by_category": {
            category: sorted(row["query_id"] for row in eligible if row["category"] == category)
            for category in CATEGORIES
        },
        "eligible_counts_by_category": {
            category: sum(row["category"] == category for row in eligible)
            for category in CATEGORIES
        },
        "rejected_reasons": dict(sorted(rejected.items())),
        "excluded_prior_mechanism_task_count": len(excluded),
    }
    print("PLAN_STATUS_ELIGIBILITY_DIAGNOSTIC=" + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True), flush=True)
    selected = select_tasks(eligible)
    selected_ids = [row["query_id"] for row in selected]
    if frozen_manifest is not None:
        frozen = json.loads(Path(frozen_manifest).read_text(encoding="utf-8"))
        if frozen.get("selected_task_ids") != selected_ids:
            raise ValueError("Deterministic eligible task selection differs from committed frozen manifest")
        if frozen.get("selection_rule") != (
            "First two eligible task IDs in lexicographic order per CostBench category after excluding all prior mechanism cohorts; "
            "eligibility requires a valid paired frozen checkpoint, a feasible incumbent suffix, and an independently reconstructed "
            "native graph optimum that confirms VALID in RETAIN and STALE in SWITCH."
        ):
            raise ValueError("Frozen selection rule does not match the implemented rule")

    manifest = {
        "schema": "paired-50-plan-status-annotation-confirmation",
        "status": "offline_frozen_no_provider_calls",
        "selection_rule": (
            "First two eligible task IDs in lexicographic order per CostBench category after excluding all prior mechanism cohorts; "
            "eligibility requires a valid paired frozen checkpoint, a feasible incumbent suffix, and an independently reconstructed "
            "native graph optimum that confirms VALID in RETAIN and STALE in SWITCH."
        ),
        "source": {
            "upstream_costbench_revision": native.UPSTREAM_SHA,
            "requests_sha256": native.sha_bytes((DATA_DIR / "model_requests_100.jsonl").read_bytes()),
            "task_registry_sha256": native.sha_bytes((DATA_DIR / "task_registry_50.json").read_bytes()),
        },
        "design": {
            "base_tasks": len(selected),
            "categories": list(CATEGORIES),
            "environment_conditions": list(ENVIRONMENTS),
            "arms": list(ARMS),
            "repetitions_per_cell": REPETITIONS,
            "full_trajectory_count": len(selected) * 2 * 2 * REPETITIONS,
            "model": native.MODEL,
            "temperature": 0,
            "thinking": "disabled",
            "max_tokens_per_call": 2048,
            "provider_calls_during_preparation": 0,
        },
        "excluded_prior_mechanism_tasks": sorted(excluded),
        "eligible_counts_by_category": diagnostic["eligible_counts_by_category"],
        "rejected_reasons": diagnostic["rejected_reasons"],
        "selected_task_ids": selected_ids,
        "tasks": [
            {"query_id": row["query_id"], "category": row["category"], "cells": row["cells"]}
            for row in selected
        ],
        "interpretation_boundary": [
            "This is a held-out confirmation within the existing 50-task CostBench cohort, not a new or unseen dataset.",
            "Tasks used in the four-arm mechanism screen, bounded-verifier confirmation, and five-task plan-handoff development screen are excluded.",
            "Both arms start from the exact same frozen checkpoint within each environment and receive the same complete graph-planner continuation; only the explicit VALID/STALE annotation differs.",
            "The annotation is oracle-derived diagnostic information, not a deployable policy result.",
            "The independent statistical unit is the base task. Repetitions and RETAIN/SWITCH conditions are nested and paired within task.",
        ],
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    built, prompt_audit = build_requests(selected, prepared, cb["official_run"])
    with (out_dir / "requests.jsonl").open("w", encoding="utf-8") as stream:
        for row in built:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    summary = {
        "status": "offline_plan_status_preflight_passed",
        "provider_calls": 0,
        "base_tasks": len(selected),
        "request_count": len(built),
        "arms": list(ARMS),
        "environments": list(ENVIRONMENTS),
        "repetitions": REPETITIONS,
        "model": native.MODEL,
        "total_reservation_units": sum(row["reservation_units"] for row in built),
        "prompt_audit": prompt_audit,
        "selected_task_ids": selected_ids,
        "manifest_sha256": native.canonical_sha(manifest),
        "request_hashes": {row["trial_id"]: row["payload_sha256"] for row in built},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "request_hashes"}, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frozen-manifest", type=Path)
    args = parser.parse_args()
    prepare(args.costbench_root.resolve(), args.out.resolve(), args.frozen_manifest)


if __name__ == "__main__":
    main()
