#!/usr/bin/env python3
"""Four-arm, first-action mechanism screen using native CostBench tools.

No provider calls are made unless --live is supplied. The script reuses the
pinned checkpoint reconstruction, CostBench tool interfaces, and native tool
execution adapter from run_official_harness.py.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "generated"
MANIFEST_PATH = HERE / "FOUR_ARM_TASK_MANIFEST.json"
sys.path.insert(0, str(HERE))

import run_official_harness as native
from four_arm_prompt_audit import build_user_messages, validate_message_arms


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_selected_trials(data_dir: Path, costbench: dict[str, Any], task_manifest: dict[str, Any]):
    requests, original_manifest, registry = native.load_frozen_inputs(data_dir)
    request_by_id = {row["trial_id"]: row for row in requests}
    original_manifest_by_id = original_manifest
    query_path = costbench["root"] / "env" / "data" / "runtime" / "queries" / "queries.json"
    query_rows = json.loads(query_path.read_text(encoding="utf-8"))
    queries = {row["query_id"].strip("<>"): row for row in query_rows}
    registry_rows = {row["task_id"]: row for row in registry["selection"]["task_ids"]}

    selected = []
    for task in task_manifest["tasks"]:
        for trial in task["condition_costs"]:
            request = request_by_id[trial["trial_id"]]
            manifest_row = original_manifest_by_id[trial["trial_id"]]
            if request["query_id"] != task["query_id"]:
                raise ValueError(f"Trial/task mismatch: {trial['trial_id']}")
            if request["checkpoint_sha256"] != task["checkpoint_sha256"]:
                raise ValueError(f"Frozen checkpoint mismatch: {task['query_id']}")
            prepared = native.prepare_trial(
                request, manifest_row, queries[task["query_id"]],
                registry_rows[task["query_id"]], costbench,
            )
            if prepared["changed_tool"] != task["changed_tool"]:
                raise ValueError(f"Changed tool mismatch: {task['query_id']}")
            if prepared["incumbent_suffix"] != task["incumbent_suffix"]:
                raise ValueError(f"Incumbent suffix mismatch: {task['query_id']}")
            if prepared["checkpoint_sha256"] != task["checkpoint_sha256"]:
                raise ValueError(f"Rebuilt checkpoint mismatch: {task['query_id']}")
            selected.append((task, request, manifest_row, prepared))
    if len(selected) != 16:
        raise ValueError(f"Expected 16 frozen environment checkpoints, got {len(selected)}")
    return selected, requests, registry


def optimal_first_actions(prepared: dict[str, Any], tolerance: float = 1e-6):
    solver_cls = None
    # The solver class is retained by the pinned CostBench module loaded by native.
    # Reconstruct it through the already prepared tool objects.
    import env.utils.solver as solver_module
    solver_cls = solver_module.GroundtruthSolver
    solver = solver_cls(prepared["tool_objects"])
    state = set(prepared["state"])
    goal = prepared["goal_type"]
    optimum = solver.solve(current_state=state, goal_types={goal})
    best_value = float(optimum.total_cost)
    values = {}
    for name, tool in prepared["tool_objects"].items():
        if not set(tool.input_types).issubset(state):
            continue
        next_state = set(state)
        next_state.add(tool.output_type)
        residual = solver.solve(current_state=next_state, goal_types={goal})
        values[name] = float(tool.cost) + float(residual.total_cost)
    optimal = sorted(name for name, value in values.items() if abs(value - best_value) <= tolerance)
    return best_value, values, optimal


def build_trials(selected, task_manifest, repetitions: int, task_limit: int, seed: int):
    task_rows = task_manifest["tasks"][:task_limit]
    allowed = {row["query_id"] for row in task_rows}
    by_trial = {(request["trial_id"]): (task, request, manifest_row, prepared)
                for task, request, manifest_row, prepared in selected if task["query_id"] in allowed}
    trials = []
    for task in task_rows:
        env_trials = [row for row in selected if row[0]["query_id"] == task["query_id"]]
        if len(env_trials) != 2:
            raise ValueError(f"Expected two environment conditions for {task['query_id']}")
        for task_row, request, manifest_row, prepared in env_trials:
            for arm in ("A", "B", "C", "D"):
                for repetition in range(1, repetitions + 1):
                    trials.append({
                        "query_id": task["query_id"],
                        "category": task["category"],
                        "environment_condition": manifest_row["condition"],
                        "prompt_condition": arm,
                        "repetition": repetition,
                        "trial_id": f"{task['query_id']}_{manifest_row['condition']}_{arm}_r{repetition}",
                        "source_trial_id": request["trial_id"],
                        "task": task,
                        "request": request,
                        "manifest_row": manifest_row,
                        "prepared": prepared,
                    })
    random.Random(seed).shuffle(trials)
    return trials


def make_payload(trial, official_run):
    prepared = trial["prepared"]
    arm_messages = build_user_messages(
        prepared,
        prepared["changed_tool"],
        float(prepared["tool_objects"][prepared["changed_tool"]].cost),
    )
    validate_message_arms(
        arm_messages,
        prepared["changed_tool"],
        float(prepared["tool_objects"][prepared["changed_tool"]].cost),
    )
    system = native.make_official_system_prompt(official_run, prepared["task"])
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": arm_messages[trial["prompt_condition"]]},
    ]
    return {
        "model": native.MODEL,
        "messages": messages,
        "tools": prepared["tool_interfaces"],
        "temperature": 0,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
    }


def offline_audit(trials, official_run):
    payload_hashes = {}
    summaries = Counter()
    for trial in trials:
        payload = make_payload(trial, official_run)
        key = trial["trial_id"]
        payload_hashes[key] = native.canonical_sha(payload)
        summaries[(trial["environment_condition"], trial["prompt_condition"])] += 1
    return {
        "status": "validated_no_model_calls",
        "trials_prepared": len(trials),
        "factorial_cells": {f"{a}/{b}": n for (a, b), n in sorted(summaries.items())},
        "unique_request_hashes": len(set(payload_hashes.values())),
        "provider_calls": 0,
        "payload_hashes": payload_hashes,
    }


async def run_live(trials, official_run, args):
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is unavailable; no API call was made.")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"Output directory is nonempty: {args.out}")

    client = official_run.AsyncOpenAI(
        base_url="https://api.deepseek.com",
        api_key=key,
        timeout=args.timeout,
    )
    budget = native.TokenBudget(args.cap)
    records = []
    request_path = args.out / "requests.jsonl"
    response_path = args.out / "responses.jsonl"
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()

    try:
        for index, trial in enumerate(trials, 1):
            payload = make_payload(trial, official_run)
            request_record = {
                "trial_id": trial["trial_id"],
                "query_id": trial["query_id"],
                "source_trial_id": trial["source_trial_id"],
                "environment_condition": trial["environment_condition"],
                "prompt_condition": trial["prompt_condition"],
                "repetition": trial["repetition"],
                "checkpoint_sha256": trial["prepared"]["checkpoint_sha256"],
                "payload": payload,
                "payload_sha256": native.canonical_sha(payload),
            }
            append_jsonl(request_path, request_record)
            started_trial = time.monotonic()
            record = {
                "trial_id": trial["trial_id"],
                "query_id": trial["query_id"],
                "source_trial_id": trial["source_trial_id"],
                "environment_condition": trial["environment_condition"],
                "prompt_condition": trial["prompt_condition"],
                "repetition": trial["repetition"],
                "checkpoint_sha256": trial["prepared"]["checkpoint_sha256"],
                "request_sha256": request_record["payload_sha256"],
                "changed_tool": trial["prepared"]["changed_tool"],
                "incumbent_suffix": trial["prepared"]["incumbent_suffix"],
            }
            try:
                response = await native.call_model(
                    client, payload["messages"], payload["tools"],
                    "required", args.max_tokens, budget,
                )
                message = response.choices[0].message
                calls = message.tool_calls or []
                record["model_reported"] = getattr(response, "model", None)
                record["provider_total_tokens"] = int(response.usage.total_tokens)
                record["assistant_content"] = message.content
                record["tool_call_count"] = len(calls)
                record["raw_tool_calls"] = [
                    {"name": call.function.name, "arguments": call.function.arguments}
                    for call in calls
                ]
                if not calls:
                    record.update({
                        "first_action": None,
                        "first_action_status": "no_tool_call",
                        "first_action_regret": None,
                        "halt_reason": "no_tool_call",
                    })
                else:
                    call = calls[0]
                    name = call.function.name
                    arguments = call.function.arguments
                    tool = trial["prepared"]["tool_objects"].get(name)
                    record["first_action"] = name
                    record["first_action_arguments"] = arguments
                    if tool is None:
                        record.update({
                            "first_action_status": "invalid_tool",
                            "first_action_regret": None,
                            "halt_reason": "invalid_tool",
                        })
                    else:
                        state = set(trial["prepared"]["state"])
                        missing = set(tool.input_types) - state
                        if missing:
                            record.update({
                                "first_action_status": "missing_inputs",
                                "missing_input_types": sorted(missing),
                                "first_action_regret": None,
                                "halt_reason": "missing_inputs",
                            })
                        else:
                            try:
                                result = official_run._execute_tool_simulation(
                                    tool_obj=tool,
                                    arguments_str=arguments,
                                    refinement_level=native.REFINEMENT_LEVEL,
                                    available_tools=trial["prepared"]["tool_objects"],
                                )
                                success = not (
                                    isinstance(result, str)
                                    and result.startswith(native.ERROR_PREFIXES)
                                )
                                record["tool_result"] = str(result)
                                record["first_action_status"] = "executed" if success else "tool_error"
                                if success:
                                    state.add(tool.output_type)
                                    baseline, action_values, optimal_actions = optimal_first_actions(trial["prepared"])
                                    import env.utils.solver as solver_module
                                    solver = solver_module.GroundtruthSolver(trial["prepared"]["tool_objects"])
                                    residual = solver.solve(
                                        current_state=state,
                                        goal_types={trial["prepared"]["goal_type"]},
                                    )
                                    action_cost = float(tool.cost)
                                    regret = action_cost + float(residual.total_cost) - baseline
                                    record.update({
                                        "first_action_cost": action_cost,
                                        "first_action_regret": round(max(0.0, regret), 8),
                                        "optimal_first_actions": optimal_actions,
                                        "action_value": round(action_cost + float(residual.total_cost), 8),
                                        "oracle_optimal_value": round(baseline, 8),
                                        "is_optimal_first_action": name in optimal_actions,
                                        "first_action_is_incumbent": name == trial["prepared"]["incumbent_suffix"][0],
                                    })
                                else:
                                    record["first_action_regret"] = None
                            except Exception as exc:
                                record.update({
                                    "first_action_status": "execution_exception",
                                    "execution_error": f"{type(exc).__name__}: {exc}",
                                    "first_action_regret": None,
                                    "halt_reason": "execution_exception",
                                })
                record.setdefault("halt_reason", "first_action_recorded")
            except Exception as exc:
                record.update({
                    "halt_reason": "api_error",
                    "api_error": f"{type(exc).__name__}: {exc}",
                    "provider_total_tokens": 0,
                    "first_action": None,
                    "first_action_status": "api_error",
                    "first_action_regret": None,
                })
            record["elapsed_seconds"] = round(time.monotonic() - started_trial, 3)
            record["accounted_tokens_after_trial"] = budget.charged
            append_jsonl(response_path, record)
            records.append(record)
            save_json(args.out / "ledger.json", {
                "status": "in_progress",
                "attempted_trials": len(records),
                "planned_trials": len(trials),
                "charged_tokens": budget.charged,
                "token_cap": budget.cap,
                "request_manifest_sha256": sha_bytes(request_path.read_bytes()),
                "started_unix": started,
                "no_retries": True,
            })
            print(json.dumps({
                "trial": index,
                "total": len(trials),
                "query_id": trial["query_id"],
                "environment": trial["environment_condition"],
                "arm": trial["prompt_condition"],
                "repetition": trial["repetition"],
                "first_action": record.get("first_action"),
                "status": record.get("first_action_status"),
                "tokens": budget.charged,
            }), flush=True)
            if record.get("halt_reason") == "api_error":
                break
            if budget.charged >= budget.cap:
                break
    finally:
        await client.close()

    summary = summarize(records, len(trials))
    summary.update({
        "token_cap": budget.cap,
        "accounted_tokens": budget.charged,
        "request_manifest_sha256": sha_bytes(request_path.read_bytes()),
        "started_unix": started,
        "finished_unix": time.time(),
        "model": native.MODEL,
        "thinking": "disabled",
        "temperature": 0,
        "no_retries": True,
    })
    save_json(args.out / "summary.json", summary)
    save_json(args.out / "ledger.json", {
        "status": summary["status"],
        "attempted_trials": len(records),
        "planned_trials": len(trials),
        "charged_tokens": budget.charged,
        "token_cap": budget.cap,
        "request_manifest_sha256": summary["request_manifest_sha256"],
        "started_unix": started,
        "finished_unix": summary["finished_unix"],
        "no_retries": True,
    })
    return summary


def summarize(records, planned):
    cells = defaultdict(list)
    for row in records:
        cells[(row["environment_condition"], row["prompt_condition"])].append(row)
    table = {}
    for (env, arm), rows in sorted(cells.items()):
        valid = [r for r in rows if r.get("first_action_status") == "executed"]
        regrets = [r["first_action_regret"] for r in valid if r.get("first_action_regret") is not None]
        table[f"{env}/{arm}"] = {
            "attempted": len(rows),
            "valid_executions": len(valid),
            "optimal_first_actions": sum(r.get("is_optimal_first_action") is True for r in valid),
            "mean_first_action_regret": (sum(regrets) / len(regrets)) if regrets else None,
            "incumbent_first_actions": sum(r.get("first_action_is_incumbent") is True for r in valid),
            "no_tool_call": sum(r.get("first_action_status") == "no_tool_call" for r in rows),
            "invalid_or_missing": sum(r.get("first_action_status") in {"invalid_tool", "missing_inputs"} for r in rows),
            "tool_errors": sum(r.get("first_action_status") in {"tool_error", "execution_exception"} for r in rows),
            "api_errors": sum(r.get("first_action_status") == "api_error" for r in rows),
        }
    return {
        "status": "complete" if len(records) == planned else "incomplete",
        "attempted_trials": len(records),
        "planned_trials": planned,
        "cell_summary": table,
        "interpretation": (
            "The first action is evaluated against the native minimum-cost continuation. "
            "Different-from-incumbent is not itself treated as a successful SWITCH."
        ),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Run the frozen four-arm CostBench mechanism screen.")
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=HERE / "four_arm_results" / "deepseek-flash")
    parser.add_argument("--live", action="store_true", help="Authorize billable DeepSeek API calls.")
    parser.add_argument("--task-limit", type=int, default=8, help="First N preselected tasks; use 2 for the planned smoke test.")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--cap", type=int, default=300000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=2048)
    return parser.parse_args()


def main():
    args = parse_args()
    if not 1 <= args.task_limit <= 8 or args.repetitions <= 0:
        raise ValueError("task-limit must be 1..8 and repetitions must be positive.")
    args.costbench_root = args.costbench_root.resolve()
    args.data_dir = args.data_dir.resolve()
    args.out = args.out.resolve()
    os.chdir(args.costbench_root)

    task_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if task_manifest["design"]["base_tasks"] != 8 or len(task_manifest["tasks"]) != 8:
        raise ValueError("Frozen four-arm manifest must contain exactly eight tasks.")
    if task_manifest["source"]["upstream_costbench_revision"] != native.UPSTREAM_SHA:
        raise ValueError("Four-arm manifest CostBench revision mismatch.")

    costbench = native.load_costbench(args.costbench_root)
    selected, _, _ = load_selected_trials(args.data_dir, costbench, task_manifest)
    trials = build_trials(selected, task_manifest, args.repetitions, args.task_limit, args.seed)
    official_run = costbench["official_run"]
    audit = offline_audit(trials, official_run)
    audit.update({
        "upstream_revision": costbench["revision"],
        "task_ids": [row["query_id"] for row in task_manifest["tasks"][:args.task_limit]],
        "repetitions": args.repetitions,
        "prompt_conditions": ["A", "B", "C", "D"],
        "environment_conditions": ["RETAIN", "SWITCH"],
        "model": native.MODEL,
        "mode": "live" if args.live else "dry_run",
        "data_sha256": sha_bytes((args.data_dir / "model_requests_100.jsonl").read_bytes()),
    })
    if not args.live:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0
    summary = asyncio.run(run_live(trials, official_run, args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
