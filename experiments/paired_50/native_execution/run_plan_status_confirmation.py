#!/usr/bin/env python3
"""Run the frozen checkpoint-level plan-status annotation confirmation on native CostBench."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import graph_planning_baseline as graph
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
    if len(requests) != expected or expected != 80:
        raise ValueError(f"Expected 80 frozen requests, found {len(requests)}")
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

    grouped = defaultdict(dict)
    for qid in task_ids:
        if manifest_task[qid]["category"] != registry_category[qid]:
            raise ValueError(f"Task category mismatch: {qid}")
        for env in prepare.ENVIRONMENTS:
            cell = manifest_task[qid]["cells"][env]
            item = prepared[(qid, env)]
            p = item["prepared"]
            optimum = graph.shortest_feasible_path(p)
            incumbent_value = prepare.path_value(p, p["state"], p["incumbent_suffix"])
            if optimum is None or incumbent_value is None:
                raise ValueError(f"Native path reconstruction failed: {qid}/{env}")
            status, gap = prepare.classify_prior_status(incumbent_value, optimum[0])
            if status != cell["prior_plan_status"] or abs(gap - float(cell["status_gap"])) > 1e-6:
                raise ValueError(f"Oracle plan-status mismatch: {qid}/{env}")
            if p["checkpoint_sha256"] != cell["checkpoint_sha256"]:
                raise ValueError(f"Checkpoint hash mismatch: {qid}/{env}")
            if list(p["incumbent_suffix"]) != cell["incumbent_plan"]:
                raise ValueError(f"Incumbent plan mismatch: {qid}/{env}")
            if list(optimum[1]) != cell["replacement_plan"]:
                raise ValueError(f"Replacement plan mismatch: {qid}/{env}")

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
        if len(payload["messages"]) != 3 or payload["messages"][-1]["role"] != "user":
            raise ValueError(f"Checkpoint-level prompt structure mismatch: {row['trial_id']}")
        expected_status = row["prior_plan_status_oracle"] if arm == "ANNOTATED" else "UNSET"
        if row["status_annotation"] != expected_status:
            raise ValueError(f"Status annotation mismatch: {row['trial_id']}")
        if not payload["messages"][-1]["content"].endswith(f"Prior-plan status: {expected_status}."):
            raise ValueError(f"Status line not present at end of prompt: {row['trial_id']}")
        p = prepared[(qid, env)]["prepared"]
        if native.canonical_sha(payload["tools"]) != native.canonical_sha(p["tool_interfaces"]):
            raise ValueError(f"Tool schema mismatch: {row['trial_id']}")
        cell = manifest_task[qid]["cells"][env]
        if row["checkpoint_sha256"] != cell["checkpoint_sha256"]:
            raise ValueError(f"Request checkpoint mismatch: {row['trial_id']}")
        if row["incumbent_plan"] != cell["incumbent_plan"] or row["updated_plan"] != cell["replacement_plan"]:
            raise ValueError(f"Request plan mismatch: {row['trial_id']}")
        if row["source_trial_id"] != cell["source_trial_id"]:
            raise ValueError(f"Source trial provenance mismatch: {row['trial_id']}")
        grouped[(qid, env, row["repetition"])][arm] = row

    for key, pair in grouped.items():
        if set(pair) != set(prepare.ARMS):
            raise ValueError(f"Incomplete status pair: {key}")
        a, b = pair["UNMARKED"], pair["ANNOTATED"]
        if a["payload"]["messages"][:-1] != b["payload"]["messages"][:-1]:
            raise ValueError(f"Checkpoint history differs across status arms: {key}")
        at = a["payload"]["messages"][-1]["content"].replace("Prior-plan status: UNSET.", "<STATUS>")
        bt = b["payload"]["messages"][-1]["content"].replace(
            f"Prior-plan status: {b['prior_plan_status_oracle']}.", "<STATUS>"
        )
        if at != bt:
            raise ValueError(f"Prompt differs outside prior-plan status label: {key}")

    return requests, manifest, prepared, cb


async def run_one(request, trial, official_run, client, budget, args, event_sink=None):
    p = trial["prepared"]
    payload = request["payload"]
    messages = copy.deepcopy(payload["messages"])
    tools = p["tool_objects"]
    state = set(p["state"])
    initial_value_result = graph.shortest_feasible_path(p)
    if initial_value_result is None:
        raise ValueError("No feasible native graph continuation from frozen checkpoint")
    start_value = float(initial_value_result[0])
    plan = list(request["updated_plan"])
    incumbent = list(request["incumbent_plan"])
    trace = []
    tokens = 0
    model_calls = 0
    provider_outcome_unknown = False
    halt = "max_steps"
    plan_cursor = 0
    incumbent_cursor = 0
    plan_deviated = False
    incumbent_deviated = False

    for step_index in range(1, args.max_steps + 1):
        if p["goal_type"] in state:
            halt = "goal_reached"
            break
        before_state = sorted(state)
        before_value = graph.shortest_feasible_path({**p, "state": set(state)})
        before_value = None if before_value is None else float(before_value[0])
        if event_sink is not None:
            event_sink({
                "event": "model_call_started", "trial_id": request["trial_id"],
                "step": step_index, "messages_sha256": native.canonical_sha(messages),
                "charged_tokens_before": budget.charged,
                "reserved_units_before": budget.reserved,
            })
        charged_before = budget.charged
        try:
            response = await native.call_model(
                client, messages, payload["tools"], "required", args.max_tokens, budget
            )
        except Exception as exc:
            halt = "reservation_cap" if "reservation_cap" in str(exc) else "api_error:" + str(exc)
            charged_delta = max(0, budget.charged - charged_before)
            provider_outcome_unknown = halt.startswith("api_error") and charged_delta == 0
            if charged_delta:
                model_calls += 1
                tokens += charged_delta
            if event_sink is not None:
                event_sink({
                    "event": "model_call_error", "trial_id": request["trial_id"],
                    "step": step_index, "error_type": type(exc).__name__,
                    "error": str(exc), "provider_outcome_unknown": provider_outcome_unknown,
                    "charged_tokens_before": charged_before,
                    "charged_tokens_after": budget.charged,
                    "provider_tokens_accounted": charged_delta,
                    "reserved_units_after": budget.reserved,
                })
            break

        model_calls += 1
        call_tokens = int(response.usage.total_tokens)
        tokens += call_tokens
        message = response.choices[0].message
        assistant_record = native.assistant_message_dict(message)
        messages.append(assistant_record)
        if event_sink is not None:
            event_sink({
                "event": "model_response", "trial_id": request["trial_id"],
                "step": step_index, "model_reported": getattr(response, "model", None),
                "provider_tokens": call_tokens, "charged_tokens_after": budget.charged,
                "assistant_message": assistant_record,
            })

        calls = message.tool_calls or []
        if len(calls) != 1:
            halt = "no_or_multiple_tool_calls"
            break
        call = calls[0]
        name = call.function.name
        arguments = call.function.arguments
        tool = tools.get(name)
        if tool is None or not set(tool.input_types).issubset(state):
            output = "[ERROR] Invalid or infeasible native tool action at the current checkpoint state."
            messages.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": output})
            if event_sink is not None:
                event_sink({
                    "event": "tool_execution", "trial_id": request["trial_id"],
                    "step": step_index, "tool": name, "arguments": arguments,
                    "success": False, "output": output,
                    "state_before": before_state, "state_after": before_state,
                })
            trace.append({
                "step": step_index, "tool": name, "arguments": arguments,
                "success": False, "cost": None, "output": output,
                "state_before": before_state, "state_after": before_state,
                "bellman_loss": None,
            })
            halt = "invalid_or_infeasible_tool"
            break

        try:
            result = official_run._execute_tool_simulation(
                tool_obj=tool, arguments_str=arguments,
                refinement_level=native.REFINEMENT_LEVEL,
                available_tools=tools,
            )
            output = str(result)
            success = not (isinstance(result, str) and result.startswith(native.ERROR_PREFIXES))
        except Exception as exc:
            output = f"[ERROR] {type(exc).__name__}: {exc}"
            success = False
        messages.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": output})
        if event_sink is not None:
            event_sink({
                "event": "tool_execution", "trial_id": request["trial_id"],
                "step": step_index, "tool": name, "arguments": arguments,
                "success": success, "output": output,
                "state_before": before_state,
                "state_after": sorted(set(before_state) | ({tool.output_type} if success else set())),
            })
        if not success:
            trace.append({
                "step": step_index, "tool": name, "arguments": arguments,
                "success": False, "cost": float(tool.cost), "output": output,
                "state_before": before_state, "state_after": before_state,
                "bellman_loss": None,
            })
            halt = "native_tool_execution_error"
            break

        state.add(tool.output_type)
        after_state = sorted(state)
        after_value_result = graph.shortest_feasible_path({**p, "state": set(state)})
        after_value = None if after_value_result is None else float(after_value_result[0])
        delta = None
        if after_value is not None and before_value is not None:
            delta = float(tool.cost) + after_value - before_value
            if delta < -1e-6:
                raise ValueError(f"Negative Bellman loss after successful action {name}: {delta}")
            delta = max(0.0, delta)
        matches_plan = not plan_deviated and plan_cursor < len(plan) and name == plan[plan_cursor]
        matches_incumbent = not incumbent_deviated and incumbent_cursor < len(incumbent) and name == incumbent[incumbent_cursor]
        trace.append({
            "step": step_index, "tool": name, "arguments": arguments, "success": True,
            "cost": float(tool.cost), "output": output,
            "state_before": before_state, "state_after": after_state,
            "V_before": before_value, "V_after": after_value,
            "bellman_loss": delta,
            "matches_updated_plan_next": matches_plan,
            "matches_incumbent_plan_next": matches_incumbent,
        })
        if matches_plan:
            plan_cursor += 1
        else:
            plan_deviated = True
        if matches_incumbent:
            incumbent_cursor += 1
        else:
            incumbent_deviated = True
        if after_value is None:
            halt = "no_feasible_completion_after_action"
            break
        if p["goal_type"] in state:
            halt = "goal_reached"
            break

    reached = p["goal_type"] in state
    executed_path = [item["tool"] for item in trace]
    continuation_cost = sum(
        float(item["cost"]) for item in trace
        if item.get("success") is True and item.get("cost") is not None
    )
    continuation_regret = continuation_cost - start_value if reached else None
    if continuation_regret is not None and continuation_regret < -1e-5:
        raise ValueError("Realized continuation is cheaper than graph reference value")
    if continuation_regret is not None:
        continuation_regret = max(0.0, continuation_regret)
    losses = [item["bellman_loss"] for item in trace if item.get("bellman_loss") is not None]
    loss_sum = sum(losses)
    if reached and all(item.get("success") for item in trace):
        if abs(loss_sum - continuation_regret) > 1e-5:
            raise ValueError("Bellman losses do not telescope to realized continuation regret")

    return {
        "trial_id": request["trial_id"], "query_id": request["query_id"],
        "category": request["category"], "environment": request["environment"],
        "arm": request["status_arm"], "status_arm": request["status_arm"],
        "status_annotation": request["status_annotation"],
        "prior_plan_status_oracle": request["prior_plan_status_oracle"],
        "repetition": request["repetition"],
        "checkpoint_sha256": request["checkpoint_sha256"],
        "payload_sha256": request["payload_sha256"],
        "initial_optimal_value": round(start_value, 8),
        "incumbent_plan": incumbent, "updated_plan": plan,
        "executed_continuation": executed_path, "trace": trace,
        "goal_reached": reached, "halt_reason": halt,
        "continuation_cost": round(continuation_cost, 8),
        "continuation_regret": None if continuation_regret is None else round(continuation_regret, 8),
        "full_path_regret": None if continuation_regret is None else round(continuation_regret, 8),
        "continuation_bellman_loss_sum": round(loss_sum, 8),
        "model_calls": model_calls, "provider_tokens": tokens,
        "provider_outcome_unknown": provider_outcome_unknown,
        "updated_plan_steps_matched": plan_cursor,
        "incumbent_plan_steps_matched": incumbent_cursor,
    }


def summarize(rows, planned, budget):
    by_cell = {}
    for env in prepare.ENVIRONMENTS:
        for arm in prepare.ARMS:
            subset = [row for row in rows if row["environment"] == env and row["arm"] == arm]
            completed = [row for row in subset if row.get("continuation_regret") is not None]
            optimal = [row for row in subset if row.get("continuation_regret") is not None and row["continuation_regret"] <= 1e-5]
            by_cell[f"{env}/{arm}"] = {
                "n": len(subset),
                "goals_reached": sum(bool(row.get("goal_reached")) for row in subset),
                "optimal_continuations": len(optimal),
                "optimal_rate": len(optimal) / len(subset) if subset else None,
                "mean_continuation_regret": round(sum(row["continuation_regret"] for row in completed) / len(completed), 8) if completed else None,
                "model_calls": sum(int(row.get("model_calls") or 0) for row in subset),
                "provider_tokens": sum(int(row.get("provider_tokens") or 0) for row in subset),
                "halt_reasons": {
                    reason: sum(row.get("halt_reason") == reason for row in subset)
                    for reason in sorted({row.get("halt_reason") for row in subset})
                },
            }

    per_task = {}
    effects = defaultdict(dict)
    for qid in sorted({row["query_id"] for row in rows}):
        per_task[qid] = {}
        for env in prepare.ENVIRONMENTS:
            for arm in prepare.ARMS:
                subset = [row for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == arm]
                regrets = [row["continuation_regret"] for row in subset if row.get("continuation_regret") is not None]
                per_task[qid][f"{env}/{arm}"] = {
                    "n": len(subset),
                    "goals_reached": sum(bool(row.get("goal_reached")) for row in subset),
                    "mean_continuation_regret": round(sum(regrets) / len(regrets), 8) if regrets else None,
                    "optimal_continuations": sum(value <= 1e-5 for value in regrets),
                }
            unmarked = [row["continuation_regret"] for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == "UNMARKED" and row.get("continuation_regret") is not None]
            annotated = [row["continuation_regret"] for row in rows if row["query_id"] == qid and row["environment"] == env and row["arm"] == "ANNOTATED" and row.get("continuation_regret") is not None]
            if unmarked and annotated:
                effects[env][qid] = round(sum(annotated) / len(annotated) - sum(unmarked) / len(unmarked), 8)

    def mean(values):
        return round(sum(values) / len(values), 8) if values else None

    task_effects = {
        env: {
            "tasks_with_both_arms": len(effects[env]),
            "per_task_regret_difference_annotated_minus_unmarked": dict(effects[env]),
            "mean_task_level_regret_difference": mean(list(effects[env].values())),
        }
        for env in prepare.ENVIRONMENTS
    }
    return {
        "status": "complete" if len(rows) == planned else "incomplete",
        "planned_trajectories": planned, "completed_trajectories": len(rows),
        "base_task_count": len(per_task),
        "independent_statistical_unit": f"base task (n={len(per_task)}); repetitions and paired environments are nested",
        "arms": list(prepare.ARMS), "environment_conditions": list(prepare.ENVIRONMENTS),
        "provider_tokens_charged": budget.charged,
        "reservation_units_requested": budget.reserved, "token_cap": budget.cap,
        "model_calls": sum(int(row.get("model_calls") or 0) for row in rows),
        "goal_reached": sum(bool(row.get("goal_reached")) for row in rows),
        "unknown_provider_outcomes": sum(bool(row.get("provider_outcome_unknown")) for row in rows),
        "by_environment_and_arm": by_cell,
        "task_level_effects": task_effects, "per_task": per_task,
        "interpretation_boundary": [
            "Both arms start from the same frozen checkpoint within each environment and receive the same complete graph-planner continuation.",
            "The only prompt manipulation is whether the remaining incumbent plan receives an explicit oracle-derived VALID/STALE status annotation or UNSET.",
            "The annotation is privileged diagnostic information, not a deployable method.",
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
    with (args.out / "requests.jsonl").open("w", encoding="utf-8") as stream:
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
            trial = {"prepared": copy.deepcopy(prepared[(request["query_id"], request["environment"])]["prepared"])}
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
                row = await run_one(request, trial, cb["official_run"], client, budget, run_args, event_sink)
            except Exception as exc:
                response_events = [item for item in trial_events if item["event"] == "model_response"]
                row = {
                    "trial_id": request["trial_id"], "query_id": request["query_id"],
                    "category": request["category"], "environment": request["environment"],
                    "arm": request["status_arm"], "status_arm": request["status_arm"],
                    "repetition": request["repetition"], "payload_sha256": request["payload_sha256"],
                    "goal_reached": False, "halt_reason": "execution_error:" + str(exc),
                    "model_calls": len(response_events),
                    "provider_tokens": sum(int(item.get("provider_tokens") or item.get("provider_tokens_accounted") or 0)
                                           for item in trial_events if item["event"] in ("model_response", "model_call_error")),
                    "provider_outcome_unknown": any(item.get("provider_outcome_unknown") for item in trial_events),
                    "continuation_regret": None,
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
    requests, manifest, prepared, cb = load_and_validate(
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
