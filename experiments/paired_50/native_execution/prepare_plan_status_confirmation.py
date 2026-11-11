#!/usr/bin/env python3
"""Freeze a two-arm plan-status annotation confirmation; offline only."""
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
PREVIOUS_HANDOFF_TASKS = {
    "Query00178", "Query00351", "Query00549", "Query00689", "Query00851"
}


def read_jsonl(path: Path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def path_value(prepared: dict, state, path):
    """Return feasible path value from a supplied typed state, else None."""
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


def make_status_message(common_action, remaining_incumbent, replacement_path, goal, status):
    if status not in {"VALID", "STALE", "UNSET"}:
        raise ValueError(f"Unexpected prior-plan status: {status}")
    return (
        "[Post-action continuation checkpoint]\n"
        f"The common first action {common_action} has already completed successfully. "
        f"Continue from its actual observation until the goal type {goal} is reached. "
        "Make one native tool call at a time and do not repeat the completed action.\n\n"
        "[Planner-provided continuation]\n"
        "An external graph planner computed the following complete feasible minimum-cost "
        "continuation from the actual post-action typed state. It is supplied as a plan "
        "reference; use the current tool definitions and observations when executing it.\n"
        "Planner continuation: " + " -> ".join(replacement_path) + "\n\n"
        "[Previously supplied plan]\n"
        "Remaining incumbent suffix: " + " -> ".join(remaining_incumbent) + "\n"
        "Status convention: VALID means this remaining incumbent suffix is still minimum-cost "
        "from the current post-action state; STALE means it remains feasible but is strictly "
        "more expensive than a minimum-cost continuation; UNSET means no validity annotation "
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
                raise ValueError(f"Reconstructed checkpoint mismatch: {task_id}")
            prepared[(task_id, source["condition"])] = {
                "request": request,
                "source": source,
                "prepared": trial,
                "category": registry_row["category"],
            }
    if len(prepared) != 100:
        raise ValueError(f"Expected 100 reconstructed native checkpoints, found {len(prepared)}")
    return requests, source_manifest, registry, request_by_id, prepared, cb


def inspect_candidate(task_id, category, response_by_trial, request_by_id, prepared, official_run):
    pair = {}
    for env in ENVIRONMENTS:
        item = prepared[(task_id, env)]
        request = item["request"]
        response = response_by_trial.get(request["trial_id"])
        if response is None:
            return None, f"missing_archived_response:{env}"
        if response.get("request_sha256") != native.canonical_sha(request):
            raise ValueError(f"Archived response request hash mismatch: {request['trial_id']}")
        if response.get("checkpoint_sha256") != item["prepared"]["checkpoint_sha256"]:
            raise ValueError(f"Archived response checkpoint mismatch: {request['trial_id']}")
        trace = response.get("trace") or []
        if not trace or trace[0].get("success") is not True:
            return None, f"first_action_not_successful:{env}"
        pair[env] = (item, response, trace[0])

    first_tools = {pair[e][2].get("tool_name") for e in ENVIRONMENTS}
    first_args = {pair[e][2].get("arguments") for e in ENVIRONMENTS}
    if len(first_tools) != 1 or len(first_args) != 1:
        return None, "paired_first_action_or_arguments_differ"
    common_action = next(iter(first_tools))
    common_arguments = next(iter(first_args))
    incumbent = pair["RETAIN"][0]["prepared"]["incumbent_suffix"]
    if not incumbent or common_action != incumbent[0]:
        return None, "common_archived_action_is_not_incumbent_first_action"
    if pair["SWITCH"][0]["prepared"]["incumbent_suffix"] != incumbent:
        raise ValueError(f"Paired incumbent suffix mismatch: {task_id}")
    if any(pair[e][0]["prepared"]["changed_tool"] == common_action for e in ENVIRONMENTS):
        return None, "changed_tool_is_consumed_by_common_prefix"
    if not isinstance(common_arguments, str) or not common_arguments.strip():
        return None, "missing_common_action_arguments"

    remaining_incumbent = list(incumbent[1:])
    if not remaining_incumbent:
        return None, "common_action_would_finish_the_task"

    cell_rows = {}
    for env in ENVIRONMENTS:
        item, response, archived_step = pair[env]
        p = item["prepared"]
        tool = p["tool_objects"].get(common_action)
        if tool is None or not set(tool.input_types).issubset(set(p["state"])):
            return None, f"common_action_not_feasible:{env}"
        if tool.output_type == p["goal_type"]:
            return None, f"common_action_is_terminal:{env}"

        # Replay from an isolated native registry. The archived result must match
        # exactly in its own source environment.
        branch = copy.deepcopy(item)
        branch_prepared = branch["prepared"]
        branch_tool = branch_prepared["tool_objects"][common_action]
        result = official_run._execute_tool_simulation(
            tool_obj=branch_tool,
            arguments_str=common_arguments,
            refinement_level=native.REFINEMENT_LEVEL,
            available_tools=branch_prepared["tool_objects"],
        )
        result_text = str(result)
        if isinstance(result, str) and result.startswith(native.ERROR_PREFIXES):
            return None, f"common_action_replay_error:{env}"
        if result_text != archived_step.get("output"):
            raise ValueError(f"Exact archived native result mismatch: {task_id}/{env}")

        post_state = set(p["state"])
        post_state.add(tool.output_type)
        optimum = graph.shortest_feasible_path({**p, "state": post_state})
        initial_optimum = graph.shortest_feasible_path(p)
        if optimum is None or initial_optimum is None or not optimum[1]:
            return None, f"no_nonempty_post_action_optimum:{env}"
        incumbent_value = path_value(p, post_state, remaining_incumbent)
        if incumbent_value is None:
            return None, f"remaining_incumbent_infeasible:{env}"
        status, status_gap = classify_prior_status(incumbent_value, optimum[0])
        expected = "VALID" if env == "RETAIN" else "STALE"
        if status != expected:
            return None, f"post_action_plan_status_mismatch:{env}:{status}"
        prefix_loss = float(tool.cost) + float(optimum[0]) - float(initial_optimum[0])
        if prefix_loss < -TOL:
            raise ValueError(f"Negative common-prefix Bellman loss: {task_id}/{env}")
        cell_rows[env] = {
            "query_id": task_id,
            "category": category,
            "environment": env,
            "common_first_action": common_action,
            "common_arguments": common_arguments,
            "common_arguments_sha256": native.sha_bytes(common_arguments.encode("utf-8")),
            "common_tool_result": result_text,
            "common_tool_result_sha256": native.sha_bytes(result_text.encode("utf-8")),
            "checkpoint_sha256": p["checkpoint_sha256"],
            "post_action_state_sha256": native.canonical_sha(sorted(post_state)),
            "common_prefix_loss": round(max(0.0, prefix_loss), 8),
            "initial_optimal_value": round(float(initial_optimum[0]), 8),
            "post_action_optimal_value": round(float(optimum[0]), 8),
            "remaining_incumbent_plan": remaining_incumbent,
            "remaining_incumbent_value": round(float(incumbent_value), 8),
            "prior_plan_status": status,
            "status_gap": round(float(status_gap), 8),
            "replacement_plan": list(optimum[1]),
            "changed_tool": p["changed_tool"],
            "changed_tool_position": (
                p["incumbent_suffix"].index(p["changed_tool"]) + 1
                if p["changed_tool"] in p["incumbent_suffix"] else "outside_incumbent"
            ),
            "tool_schema_sha256": native.canonical_sha(p["tool_interfaces"]),
            "source_trial_id": item["source"]["trial_id"],
            "source_response_trial_id": response["trial_id"],
        }
    return cell_rows, None


def select_tasks(candidates):
    by_category = defaultdict(list)
    for row in candidates:
        by_category[row["category"]].append(row)
    selected = []
    for category in sorted(by_category):
        selected.extend(sorted(by_category[category], key=lambda x: x["query_id"])[:TASKS_PER_CATEGORY])
    counts = defaultdict(int)
    for row in selected:
        counts[row["category"]] += 1
    if len(selected) != 10 or any(counts[c] != TASKS_PER_CATEGORY for c in (
        "accommodation", "attraction", "dining", "shopping", "transportation"
    )):
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
            common_action = cell["common_first_action"]
            common_id = f"common_{qid}_{env}"
            base_messages = [
                {"role": "system", "content": native.make_official_system_prompt(official_run, p["task"])},
            ]
            user_message = native.make_checkpoint_user_message(p)
            base_messages.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": common_id, "type": "function",
                    "function": {"name": common_action, "arguments": cell["common_arguments"]},
                }]},
                {"role": "tool", "tool_call_id": common_id, "name": common_action,
                 "content": cell["common_tool_result"]},
            ])
            prompts = {}
            for arm in ARMS:
                label = cell["prior_plan_status"] if arm == "ANNOTATED" else "UNSET"
                final_message = make_status_message(
                    common_action, cell["remaining_incumbent_plan"],
                    cell["replacement_plan"], p["goal_type"], label,
                )
                messages = copy.deepcopy(base_messages)
                messages.append({"role": "user", "content": final_message})
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
                raise ValueError(f"Shared history differs across status arms: {qid}/{env}")
            unmarked_text = prompts["UNMARKED"]["messages"][-1]["content"]
            annotated_text = prompts["ANNOTATED"]["messages"][-1]["content"]
            expected_unmarked = "Prior-plan status: UNSET."
            expected_annotated = f"Prior-plan status: {cell['prior_plan_status']}."
            if unmarked_text.replace(expected_unmarked, "<STATUS>") != annotated_text.replace(expected_annotated, "<STATUS>"):
                raise ValueError(f"Status arms differ outside the single status label: {qid}/{env}")
            prompt_audit.append({
                "query_id": qid, "environment": env,
                "same_pre_status_history": True,
                "same_tool_schema": True,
                "same_replacement_plan": True,
                "status_only_difference": True,
                "unmarked_payload_sha256": prompts["UNMARKED"]["payload_sha256"],
                "annotated_payload_sha256": prompts["ANNOTATED"]["payload_sha256"],
            })
            for arm in ARMS:
                for repetition in range(1, repetitions + 1):
                    row = {
                        "trial_id": f"{qid}_{env}_{arm}_r{repetition}",
                        "query_id": qid,
                        "category": task["category"],
                        "environment": env,
                        "arm": "B",  # Reuse the validated full-plan continuation executor.
                        "status_arm": arm,
                        "status_annotation": cell["prior_plan_status"] if arm == "ANNOTATED" else "UNSET",
                        "repetition": repetition,
                        "checkpoint_sha256": cell["checkpoint_sha256"],
                        "common_first_action": common_action,
                        "common_arguments": cell["common_arguments"],
                        "common_tool_result": cell["common_tool_result"],
                        "common_tool_result_sha256": cell["common_tool_result_sha256"],
                        "post_action_state_sha256": cell["post_action_state_sha256"],
                        "common_prefix_loss": cell["common_prefix_loss"],
                        "initial_optimal_value": cell["initial_optimal_value"],
                        "updated_plan": cell["replacement_plan"],
                        "remaining_incumbent_after_common_action": cell["remaining_incumbent_plan"],
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
                    }
                    requests.append(row)
    expected = len(selected) * len(ENVIRONMENTS) * len(ARMS) * repetitions
    if len(requests) != expected:
        raise ValueError(f"Expected {expected} requests, got {len(requests)}")
    return requests, prompt_audit


def prepare(costbench_root, responses_path, out_dir, frozen_manifest=None):
    responses = read_jsonl(responses_path)
    if len(responses) != 100:
        raise ValueError(f"Expected 100 archived native trajectories, got {len(responses)}")
    response_by_trial = {row["trial_id"]: row for row in responses}
    if len(response_by_trial) != 100:
        raise ValueError("Duplicate archived native response trial IDs")

    requests, source_manifest, registry, request_by_id, prepared, cb = reconstruct_all(costbench_root)
    if len(requests) != 100:
        raise ValueError("Frozen request cohort is not 100 rows")
    for response in responses:
        if response["trial_id"] not in request_by_id:
            raise ValueError(f"Unexpected archived trial: {response['trial_id']}")

    excluded = previous_task_exclusions()
    categories = {row["task_id"]: row["category"] for row in registry["selection"]["task_ids"]}
    eligible = []
    rejected = defaultdict(int)
    candidate_cells = {}
    for qid in sorted(categories):
        if qid in excluded:
            rejected["previously_used_mechanism_task"] += 1
            continue
        cells, reason = inspect_candidate(
            qid, categories[qid], response_by_trial, request_by_id, prepared, cb["official_run"]
        )
        if reason:
            rejected[reason] += 1
            continue
        candidate = {"query_id": qid, "category": categories[qid], "cells": cells}
        eligible.append(candidate)
        candidate_cells[qid] = cells

    selected = select_tasks(eligible)
    selected_ids = [row["query_id"] for row in selected]
    if frozen_manifest is not None:
        frozen = json.loads(Path(frozen_manifest).read_text(encoding="utf-8"))
        if frozen.get("selected_task_ids") != selected_ids:
            raise ValueError("Deterministic eligible task selection differs from committed frozen manifest")
        if frozen.get("selection_rule") != "First two eligible task IDs in lexicographic order per CostBench category after excluding all prior mechanism cohorts; eligibility requires the archived paired first action to be identical, incumbent-first, successful and nonterminal, and requires post-action incumbent status VALID in RETAIN and STALE in SWITCH.":
            raise ValueError("Frozen selection rule does not match the implemented rule")

    manifest = {
        "schema": "paired-50-plan-status-annotation-confirmation",
        "status": "offline_frozen_no_provider_calls",
        "selection_rule": "First two eligible task IDs in lexicographic order per CostBench category after excluding all prior mechanism cohorts; eligibility requires the archived paired first action to be identical, incumbent-first, successful and nonterminal, and requires post-action incumbent status VALID in RETAIN and STALE in SWITCH.",
        "source": {
            "upstream_costbench_revision": native.UPSTREAM_SHA,
            "requests_sha256": native.sha_bytes((DATA_DIR / "model_requests_100.jsonl").read_bytes()),
            "task_registry_sha256": native.sha_bytes((DATA_DIR / "task_registry_50.json").read_bytes()),
            "archived_response_count": len(responses),
            "archived_responses_sha256": native.sha_bytes(Path(responses_path).read_bytes()),
        },
        "design": {
            "base_tasks": len(selected),
            "categories": sorted({row["category"] for row in selected}),
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
        "eligible_counts_by_category": {
            category: sum(row["category"] == category for row in eligible)
            for category in sorted(set(categories.values()))
        },
        "rejected_reasons": dict(sorted(rejected.items())),
        "selected_task_ids": selected_ids,
        "tasks": [
            {
                "query_id": row["query_id"],
                "category": row["category"],
                "cells": row["cells"],
            }
            for row in selected
        ],
        "interpretation_boundary": [
            "This is a held-out confirmation within the plan-handoff mechanism study, not a new or unseen CostBench dataset; all tasks belong to the existing 50-task cohort.",
            "The selection is conditioned on the archived baseline having executed the same incumbent first action with the same arguments in both paired environments, so conclusions apply to this controlled post-action continuation cohort.",
            "The graph planner supplies the same complete minimum-cost continuation to both arms. The annotated arm additionally receives an oracle-derived VALID or STALE status for the remaining incumbent plan; this is a privileged diagnostic intervention, not a deployable method.",
            "The independent statistical unit is the base task. Repetitions and RETAIN/SWITCH conditions are paired within task.",
        ],
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The native system prompt is shared across status arms and uses the pinned upstream template.
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
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frozen-manifest", type=Path)
    args = parser.parse_args()
    prepare(args.costbench_root.resolve(), args.responses.resolve(), args.out.resolve(), args.frozen_manifest)


if __name__ == "__main__":
    main()
