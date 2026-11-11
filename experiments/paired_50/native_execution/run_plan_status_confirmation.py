#!/usr/bin/env python3
"""Run the frozen plan-status annotation continuation experiment on native CostBench."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import prepare_plan_status_confirmation as prepare
import run_official_harness as native
import run_plan_handoff_experiment as handoff


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def load_and_validate(requests_path, manifest_path, costbench_root):
    requests = read_jsonl(requests_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema") != "paired-50-plan-status-annotation-confirmation":
        raise ValueError("Unexpected frozen plan-status manifest schema")
    task_ids = manifest.get("selected_task_ids", [])
    expected = len(task_ids) * 2 * 2 * 2
    if len(requests) != expected or expected < 64:
        raise ValueError(f"Expected at least 64 frozen requests, found {len(requests)}")
    ids = [row["trial_id"] for row in requests]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate plan-status trial IDs")
    expected_cells = {
        (qid, env, arm, rep)
        for qid in task_ids
        for env in prepare.ENVIRONMENTS
        for arm in prepare.ARMS
        for rep in (1, 2)
    }
    actual_cells = {
        (row["query_id"], row["environment"], row["status_arm"], row["repetition"])
        for row in requests
    }
    if actual_cells != expected_cells:
        raise ValueError("Frozen request matrix is incomplete or contains unexpected cells")

    all_requests, source_manifest, registry, request_by_id, prepared, cb = prepare.reconstruct_all(
        Path(costbench_root).resolve()
    )
    registry_category = {row["task_id"]: row["category"] for row in registry["selection"]["task_ids"]}
    if set(task_ids) - set(registry_category):
        raise ValueError("Frozen task IDs are absent from the source registry")

    manifest_task = {row["query_id"]: row for row in manifest["tasks"]}
    if set(manifest_task) != set(task_ids):
        raise ValueError("Manifest task records differ from selected_task_ids")
    for qid in task_ids:
        if manifest_task[qid]["category"] != registry_category[qid]:
            raise ValueError(f"Task category mismatch: {qid}")
        for env in prepare.ENVIRONMENTS:
            cell = manifest_task[qid]["cells"][env]
            p = prepared[(qid, env)]["prepared"]
            if p["checkpoint_sha256"] != cell["checkpoint_sha256"]:
                raise ValueError(f"Checkpoint hash mismatch: {qid}/{env}")
            expected_remaining = (
                p["incumbent_suffix"][1:]
                if cell["common_first_action"] == p["incumbent_suffix"][0]
                else p["incumbent_suffix"]
            )
            if expected_remaining != cell["remaining_incumbent_plan"]:
                raise ValueError(f"Incumbent suffix mismatch: {qid}/{env}")

    grouped = defaultdict(dict)
    for row in requests:
        qid, env, arm = row["query_id"], row["environment"], row["status_arm"]
        if row["arm"] != "B":
            raise ValueError("Continuation executor must receive the full-plan arm")
        if row["category"] != registry_category[qid]:
            raise ValueError(f"Request category mismatch: {qid}")
        if row["trial_id"] != f"{qid}_{env}_{arm}_r{row['repetition']}":
            raise ValueError("Trial ID does not match frozen factors")
        if native.canonical_sha(row["payload"]) != row["payload_sha256"]:
            raise ValueError(f"Payload hash mismatch: {row['trial_id']}")
        payload = row["payload"]
        if payload.get("model") != native.MODEL or payload.get("temperature") != 0 or payload.get("max_tokens") != 2048:
            raise ValueError(f"Model configuration mismatch: {row['trial_id']}")
        if payload["messages"][-1]["role"] != "user":
            raise ValueError("Final status message missing")
        expected_status = row["prior_plan_status_oracle"] if arm == "ANNOTATED" else "UNSET"
        if row["status_annotation"] != expected_status:
            raise ValueError(f"Status annotation mismatch: {row['trial_id']}")
        expected_line = f"Prior-plan status: {expected_status}."
        if not payload["messages"][-1]["content"].endswith(expected_line):
            raise ValueError(f"Status line not present at the end of prompt: {row['trial_id']}")
        p = prepared[(qid, env)]["prepared"]
        if native.canonical_sha(payload["tools"]) != native.canonical_sha(p["tool_interfaces"]):
            raise ValueError(f"Tool schema mismatch: {row['trial_id']}")
        cell = manifest_task[qid]["cells"][env]
        for key in (
            "common_first_action", "common_arguments", "common_tool_result",
            "common_tool_result_sha256", "post_action_state_sha256",
            "remaining_incumbent_after_common_action",
        ):
            request_key = {
                "remaining_incumbent_after_common_action": "remaining_incumbent_plan"
            }.get(key, key)
            if row[key] != cell[request_key]:
                raise ValueError(f"Frozen common action mismatch ({key}): {row['trial_id']}")
        if row["updated_plan"] != cell["replacement_plan"]:
            raise ValueError(f"Replacement plan mismatch: {row['trial_id']}")
        grouped[(qid, env, row["repetition"])][arm] = row

    for key, pair in grouped.items():
        if set(pair) != set(prepare.ARMS):
            raise ValueError(f"Incomplete status pair: {key}")
        a, b = pair["UNMARKED"], pair["ANNOTATED"]
        if a["payload"]["messages"][:-1] != b["payload"]["messages"][:-1]:
            raise ValueError(f"Pre-status history differs: {key}")
        at = a["payload"]["messages"][-1]["content"]
        bt = b["payload"]["messages"][-1]["content"]
        at = at.replace("Prior-plan status: UNSET.", "<STATUS>")
        bt = bt.replace(f"Prior-plan status: {b['prior_plan_status_oracle']}.", "<STATUS>")
        if at != bt:
            raise ValueError(f"Prompt differs outside prior-plan status label: {key}")

    # Replay each unique common action again in a fresh branch before any paid call.
    restoration_rows = []
    for qid in task_ids:
        for env in prepare.ENVIRONMENTS:
            rows = [r for r in requests if r["query_id"] == qid and r["environment"] == env]
            request = rows[0]
            trial = handoff.clone_trial_for_branch({"prepared": prepared[(qid, env)]["prepared"]})
            p = trial["prepared"]
            tool = p["tool_objects"][request["common_first_action"]]
            result = cb["official_run"]._execute_tool_simulation(
                tool_obj=tool, arguments_str=request["common_arguments"],
                refinement_level=native.REFINEMENT_LEVEL,
                available_tools=p["tool_objects"],
            )
            if str(result) != request["common_tool_result"]:
                raise ValueError(f"Common action result mismatch: {qid}/{env}")
            state = set(p["state"])
            state.add(tool.output_type)
            if native.canonical_sha(sorted(state)) != request["post_action_state_sha256"]:
                raise ValueError(f"Post-action state mismatch: {qid}/{env}")
            restoration_rows.append({
                "query_id": qid, "environment": env,
                "exact_result_match": True, "post_action_state_match": True,
            })

    return requests, manifest, prepared, cb, restoration_rows


def summarize(rows, planned, budget):
    by_cell = {}
    for env in prepare.ENVIRONMENTS:
        for arm in prepare.ARMS:
            subset = [row for row in rows if row["environment"] == env and row["arm"] == arm]
            completed = [row for row in subset if row.get("continuation_regret") is not None]
            by_cell[f"{env}/{arm}"] = {
                "n": len(subset),
                "goals_reached": sum(bool(row.get("goal_reached")) for row in subset),
                "optimal_continuations": sum(
                    row.get("continuation_regret") is not None and row["continuation_regret"] <= 1e-5
                    for row in subset
                ),
                "optimal_rate": (
                    sum(row.get("continuation_regret") is not None and row["continuation_regret"] <= 1e-5 for row in subset) / len(subset)
                    if subset else None
                ),
                "mean_continuation_regret": (
                    round(sum(row["continuation_regret"] for row in completed) / len(completed), 8)
                    if completed else None
                ),
                "mean_full_path_regret": (
                    round(sum(row["full_path_regret"] for row in subset if row.get("full_path_regret") is not None) /
                          sum(row.get("full_path_regret") is not None for row in subset), 8)
                    if any(row.get("full_path_regret") is not None for row in subset) else None
                ),
                "model_calls": sum(int(row.get("model_calls") or 0) for row in subset),
                "provider_tokens": sum(int(row.get("provider_tokens") or 0) for row in subset),
                "halt_reasons": {
                    reason: sum(row.get("halt_reason") == reason for row in subset)
                    for reason in sorted({row.get("halt_reason") for row in subset})
                },
            }

    per_task = {}
    task_effects = defaultdict(dict)
    for qid in sorted({row["query_id"] for row in rows}):
        per_task[qid] = {}
        for env in prepare.ENVIRONMENTS:
            for arm in prepare.ARMS:
                subset = [row for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == arm]
                regrets = [row["continuation_regret"] for row in subset if row.get("continuation_regret") is not None]
                optimal = [row.get("continuation_regret") is not None and row["continuation_regret"] <= 1e-5 for row in subset]
                per_task[qid][f"{env}/{arm}"] = {
                    "n": len(subset),
                    "goals_reached": sum(bool(row.get("goal_reached")) for row in subset),
                    "optimal_continuations": sum(optimal),
                    "mean_continuation_regret": round(sum(regrets) / len(regrets), 8) if regrets else None,
                }
            unmarked = [row["continuation_regret"] for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == "UNMARKED" and row.get("continuation_regret") is not None]
            annotated = [row["continuation_regret"] for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == "ANNOTATED" and row.get("continuation_regret") is not None]
            if unmarked and annotated:
                task_effects[env][qid] = round(sum(annotated)/len(annotated) - sum(unmarked)/len(unmarked), 8)

    def mean(values):
        return round(sum(values) / len(values), 8) if values else None

    effects = {
        env: {
            "tasks_with_both_arms": len(task_effects[env]),
            "per_task_regret_difference_annotated_minus_unmarked": dict(task_effects[env]),
            "mean_task_level_regret_difference": mean(list(task_effects[env].values())),
        }
        for env in prepare.ENVIRONMENTS
    }
    return {
        "status": "complete" if len(rows) == planned else "incomplete",
        "planned_trajectories": planned,
        "completed_trajectories": len(rows),
        "base_task_count": len(per_task),
        "independent_statistical_unit": f"base task (n={len(per_task)}); repetitions and paired environments are nested",
        "arms": list(prepare.ARMS),
        "environment_conditions": list(prepare.ENVIRONMENTS),
        "provider_tokens_charged": budget.charged,
        "reservation_units_requested": budget.reserved,
        "token_cap": budget.cap,
        "model_calls": sum(int(row.get("model_calls") or 0) for row in rows),
        "goal_reached": sum(bool(row.get("goal_reached")) for row in rows),
        "unknown_provider_outcomes": sum(bool(row.get("provider_outcome_unknown")) for row in rows),
        "by_environment_and_arm": by_cell,
        "task_level_effects": effects,
        "per_task": per_task,
        "interpretation_boundary": [
            "Both arms receive the same complete planner-computed continuation, the same old plan, the same common native action and exact observation, and the same tool schemas.",
            "The only prompt manipulation is whether the remaining incumbent plan receives an explicit oracle-derived VALID/STALE annotation or an UNSET annotation.",
            "The annotation is privileged diagnostic information, not a deployable policy result.",
            "The independent statistical unit is the base task; repetitions and RETAIN/SWITCH conditions are paired within task.",
        ],
    }


async def run_live(requests, prepared, cb, args):
    from openai import AsyncOpenAI
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError("Output directory must be empty; do not overwrite prior records")
    args.out.mkdir(parents=True, exist_ok=True)
    budget = native.TokenBudget(args.cap)
    response_path = args.out / "responses.jsonl"
    event_path = args.out / "call_events.jsonl"
    ledger_path = args.out / "ledger.json"
    request_path = args.out / "requests.jsonl"
    with request_path.open("w", encoding="utf-8") as stream:
        for row in requests:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    rows = []

    def persist(status, active_trial=None, active_calls=0, active_tokens=0):
        handoff.save_json_durable(ledger_path, {
            "status": status,
            "completed_trajectories": len(rows),
            "planned_trajectories": len(requests),
            "completed_trial_ids": [row["trial_id"] for row in rows],
            "active_trial_id": active_trial,
            "active_trial_model_responses": active_calls,
            "active_trial_provider_tokens": active_tokens,
            "provider_tokens_charged_this_run": budget.charged,
            "reservation_units_requested_this_run": budget.reserved,
            "approved_total_token_cap": args.cap,
            "prior_orphaned_attempt_reserve": 0,
            "effective_new_run_token_cap": budget.cap,
            "no_automatic_retries": True,
        })

    persist("in_progress")
    async with AsyncOpenAI(base_url="https://api.deepseek.com", api_key=key, timeout=args.timeout) as client:
        for index, request in enumerate(requests, 1):
            trial = handoff.clone_trial_for_branch({"prepared": prepared[(request["query_id"], request["environment"])]["prepared"]})
            start = time.monotonic()
            trial_events = []
            handoff.append_jsonl(event_path, {
                "event": "trial_started", "trial_id": request["trial_id"],
                "trial_index": index, "planned_trials": len(requests),
                "request_payload_sha256": request["payload_sha256"],
            })

            def event_sink(event):
                trial_events.append(event)
                handoff.append_jsonl(event_path, event)
                persist(
                    "in_progress", request["trial_id"],
                    sum(item["event"] == "model_response" for item in trial_events),
                    sum(int(item.get("provider_tokens") or 0) for item in trial_events),
                )

            try:
                run_args = SimpleNamespace(max_steps=args.max_steps, max_tokens=args.max_tokens)
                row = await handoff.run_one(
                    request, trial, cb["official_run"], client, budget, run_args,
                    event_sink=event_sink,
                )
                row["arm"] = request["status_arm"]
                row["status_arm"] = request["status_arm"]
                row["status_annotation"] = request["status_annotation"]
                row["prior_plan_status_oracle"] = request["prior_plan_status_oracle"]
            except Exception as exc:
                responses = [item for item in trial_events if item["event"] == "model_response"]
                row = {
                    "trial_id": request["trial_id"], "query_id": request["query_id"],
                    "environment": request["environment"], "arm": request["status_arm"],
                    "status_arm": request["status_arm"], "repetition": request["repetition"],
                    "payload_sha256": request["payload_sha256"], "goal_reached": False,
                    "halt_reason": "execution_error:" + str(exc),
                    "model_calls": len(responses),
                    "provider_tokens": sum(int(item.get("provider_tokens") or item.get("provider_tokens_accounted") or 0)
                                           for item in trial_events if item["event"] in ("model_response", "model_call_error")),
                    "provider_outcome_unknown": any(item.get("provider_outcome_unknown") for item in trial_events),
                    "continuation_regret": None,
                    "partial_call_events": trial_events,
                }
            row["elapsed_seconds"] = round(time.monotonic() - start, 3)
            row["provider_tokens_charged_after_trial"] = budget.charged
            rows.append(row)
            handoff.append_jsonl(response_path, row)
            persist("incomplete" if len(rows) < len(requests) else "complete")
            print(json.dumps({
                "completed": len(rows), "planned": len(requests),
                "trial_id": request["trial_id"], "goal_reached": row.get("goal_reached"),
                "halt_reason": row.get("halt_reason"),
                "provider_tokens_charged": budget.charged,
            }), flush=True)
            reason = str(row.get("halt_reason", ""))
            if reason == "reservation_cap" or reason.startswith("api_error") or reason.startswith("execution_error"):
                break

    summary = summarize(rows, len(requests), budget)
    summary.update({
        "approved_total_token_cap": args.cap,
        "call_event_journal": "call_events.jsonl",
        "resumed_from_completed_trajectories": 0,
    })
    handoff.save_json_durable(args.out / "summary.json", summary)
    persist("complete" if len(rows) == len(requests) else "incomplete")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=int, default=1_200_000)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.max_tokens != 2048:
        parser.error("The frozen experiment requires max_tokens=2048")
    requests, manifest, prepared, cb, restoration = load_and_validate(
        args.requests.resolve(), args.manifest.resolve(), args.costbench_root.resolve()
    )
    if not args.live:
        print(json.dumps({
            "status": "validated_no_provider_calls",
            "provider_calls": 0,
            "trajectories": len(requests),
            "base_tasks": len(manifest["selected_task_ids"]),
            "arms": list(prepare.ARMS),
            "environments": list(prepare.ENVIRONMENTS),
            "restored_common_actions": len(restoration),
            "model": native.MODEL,
            "max_tokens": args.max_tokens,
        }, ensure_ascii=False, indent=2))
        return
    result = asyncio.run(run_live(requests, prepared, cb, args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
