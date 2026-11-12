"""Frozen 32-trajectory development screen; paid calls require explicit --execute."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from .errors import BudgetExceeded, NativeOutcomeUnknown, ProviderOutcomeUnknown
from .policy_input import parse_public_tool_interfaces
from .provider import BudgetedDeepSeekProvider
from .run_complete_candidate import (
    execute_native_tool_with_capture, load_native_trial, make_observation_history,
    make_policy_input_from_prepared, run_complete_candidate,
)
from .scoring_logging import (
    append_jsonl_durable, path_value, score_trajectory, summarize_records,
    write_json_atomic,
)
from .prepare_development_screen import MANIFEST_PATH, prepare

DEFAULT_OUTPUT = Path("outputs/complete_candidate_development_screen")


def build_schedule(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic counterbalanced schedule; the base task is the analysis unit."""
    methods = [row["id"] for row in manifest["design"]["methods"]]
    if set(methods) != {"repair_plus_fresh", "fresh_plus_fresh"}:
        raise ValueError("the frozen manifest must contain both candidate methods")
    schedule = []
    for task_index, task in enumerate(manifest["selection"]["tasks"]):
        conditions = ("RETAIN", "SWITCH") if task_index % 2 == 0 else ("SWITCH", "RETAIN")
        for condition_index, condition in enumerate(conditions):
            method_order = methods if (task_index + condition_index) % 2 == 0 else list(reversed(methods))
            for method_order_index, method in enumerate(method_order):
                schedule.append({
                    "query_id": task["query_id"], "condition": condition, "method": method,
                    "task_index": task_index, "condition_order_index": condition_index,
                    "method_order_index": method_order_index,
                    "trial_id": task["trial_ids"][condition],
                    "checkpoint_sha256": task["checkpoint_sha256"],
                })
    expected = int(manifest["design"]["full_native_trajectories"])
    if len(schedule) != expected:
        raise ValueError(f"schedule has {len(schedule)} cells; expected {expected}")
    keys = [(x["query_id"], x["condition"], x["method"]) for x in schedule]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate task-condition-method cell")
    return schedule


def _write_summary(out: Path, records: list[dict[str, Any]],
                   provider: BudgetedDeepSeekProvider, status: str,
                   expected: int, error: str | None = None) -> dict[str, Any]:
    by_method = {}
    for method in ("repair_plus_fresh", "fresh_plus_fresh"):
        subset = [row["score"] for row in records if row["method"] == method]
        if subset and {row["condition"] for row in subset} == {"RETAIN", "SWITCH"}:
            by_method[method] = summarize_records(subset)
        elif subset:
            by_method[method] = {"trajectory_count": len(subset),
                                 "awaiting_both_conditions": True}
    summary = {
        "schema": "complete-candidate-development-screen-results-v1",
        "status": status, "expected_trajectories": expected,
        "completed_trajectories": len(records),
        "base_tasks": len({row["query_id"] for row in records}),
        "analysis_unit": "base_task",
        "repetitions_are_not_independent": True,
        "methods": by_method, "provider_budget": provider.snapshot(),
        "error": error,
    }
    write_json_atomic(out / "summary.json", summary)
    return summary


async def _run_live(args: argparse.Namespace, manifest: dict[str, Any],
                    out: Path) -> dict[str, Any]:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is unavailable; no provider request was sent")
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url="https://api.deepseek.com", api_key=key,
                         timeout=args.timeout, max_retries=0)
    provider = BudgetedDeepSeekProvider(
        client, audit_path=out / "provider_events.jsonl",
        token_cap=args.token_cap, model=manifest["design"]["model"],
    )
    schedule = build_schedule(manifest)
    records: list[dict[str, Any]] = []
    response_path = out / "responses.jsonl"
    native_event_path = out / "native_events.jsonl"
    try:
        for run_index, cell in enumerate(schedule, start=1):
            native, costbench, prepared, query = load_native_trial(
                args.costbench_root, cell["query_id"], cell["condition"],
                minimum_plan_length=1,
            )
            if prepared["trial_id"] != cell["trial_id"]:
                raise ValueError(f"frozen trial changed for {cell['query_id']} {cell['condition']}")
            if prepared["checkpoint_sha256"] != cell["checkpoint_sha256"]:
                raise ValueError(f"frozen checkpoint changed for {cell['query_id']}")

            history = make_observation_history(prepared, query, native)
            policy_input = make_policy_input_from_prepared(prepared, history)
            provider.set_context(
                run_index=str(run_index), trial_id=cell["trial_id"],
                query_id=cell["query_id"], condition_for_posthoc_only=cell["condition"],
                method=cell["method"],
            )
            official_prompt = native.make_official_system_prompt(
                costbench["official_run"], prepared["task"]
            )

            def execute(**kwargs):
                event = {
                    "event": "native_call_started", "run_index": run_index,
                    "trial_id": cell["trial_id"], "query_id": cell["query_id"],
                    "method": cell["method"], "tool_name": kwargs["tool_name"],
                    "arguments": kwargs["arguments"],
                }
                append_jsonl_durable(native_event_path, event)
                try:
                    native_result = execute_native_tool_with_capture(
                        costbench["official_run"],
                        tool_obj=prepared["tool_objects"][kwargs["tool_name"]],
                        arguments_str=kwargs["arguments_str"], refinement_level=2,
                        available_tools=prepared["tool_objects"],
                    )
                except Exception as exc:
                    append_jsonl_durable(native_event_path, {
                        **event, "event": "native_outcome_unknown",
                        "error_type": type(exc).__name__, "error": str(exc)[:1000],
                    })
                    raise NativeOutcomeUnknown(
                        f"native outcome unknown for {kwargs['tool_name']}: {exc}"
                    ) from exc
                append_jsonl_durable(native_event_path, {
                    **event, "event": "native_call_returned",
                    "success": native_result.success, "observation": native_result.observation,
                    "output_type": native_result.output_type, "output_id": native_result.output_id,
                    "error": native_result.error,
                })
                if native_result.success and not native_result.output_id:
                    raise NativeOutcomeUnknown(
                        f"{kwargs['tool_name']} succeeded without a captured native output ID"
                    )
                return native_result

            result = await run_complete_candidate(
                policy_input, candidate_completion=provider.candidate_completion(),
                argument_completion=provider.argument_completion(), native_execute=execute,
                native_tool_objects=prepared["tool_objects"],
                candidate_strategy=cell["method"],
                max_tool_steps=manifest["design"]["maximum_tool_steps_per_trajectory"],
                native_system_prompt=official_prompt,
            )
            contracts = parse_public_tool_interfaces(prepared["tool_interfaces"])
            costs = {name: contract.cost for name, contract in contracts.items()}
            oracle_value = path_value(prepared["native_optimal_path"], costs)
            score = score_trajectory(
                task_id=f"{cell['query_id']}::{cell['method']}",
                condition=cell["condition"], decision=result.decision.action,
                goal_reached=result.goal_reached, executed_path=result.executed_path,
                committed_path=result.decision.selected_plan or (),
                incumbent_path=prepared["incumbent_suffix"],
                current_tool_costs=costs, oracle_optimal_value=oracle_value,
                usage={
                    "planning_calls": result.planning_calls,
                    "parameter_calls": result.parameter_calls,
                    "planning_tokens": result.planning_tokens,
                    "parameter_tokens": result.parameter_tokens,
                    "total_model_calls": result.planning_calls + result.parameter_calls,
                    "total_tokens": result.planning_tokens + result.parameter_tokens,
                    "decision_latency_seconds": result.decision_latency_seconds,
                },
            )
            record = {
                "run_index": run_index, "trial_id": cell["trial_id"],
                "query_id": cell["query_id"],
                "condition_for_posthoc_only": cell["condition"],
                "method": cell["method"], "task_index": cell["task_index"],
                "checkpoint_sha256": cell["checkpoint_sha256"],
                "model": manifest["design"]["model"],
                "temperature": manifest["design"]["temperature"],
                "thinking": manifest["design"]["thinking"],
                "status": result.status, "result": result.to_record(), "score": score,
                "provider_budget_after_trial": provider.snapshot(),
                "upstream_costbench_revision": manifest["design"]["upstream_costbench_revision"],
            }
            append_jsonl_durable(response_path, record)
            records.append(record)
            _write_summary(out, records, provider, "running", len(schedule))
        return _write_summary(out, records, provider, "complete", len(schedule))
    except (ProviderOutcomeUnknown, NativeOutcomeUnknown, BudgetExceeded) as exc:
        _write_summary(out, records, provider, "stopped_without_retry", len(schedule),
                       f"{type(exc).__name__}: {exc}")
        raise
    except Exception as exc:
        _write_summary(out, records, provider, "failed", len(schedule),
                       f"{type(exc).__name__}: {exc}")
        raise
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Frozen 32-trajectory screen. No provider calls unless --execute is supplied."
    )
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--token-cap", type=int, default=1_200_000)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly authorize live DeepSeek requests and native execution.")
    args = parser.parse_args()
    args.costbench_root = args.costbench_root.resolve()
    args.out = args.out.resolve()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    frozen_cap = int(manifest["design"]["planned_provider_token_hard_cap"])
    if args.token_cap <= 0 or args.token_cap > frozen_cap:
        raise ValueError(f"--token-cap must be between 1 and the frozen cap {frozen_cap}")
    if args.timeout <= 0:
        raise ValueError("--timeout must be positive")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"Output directory is nonempty: {args.out}")

    # Rebuild all paired checkpoints and exact policy prompts before any provider setup.
    preflight = prepare(args)
    schedule = build_schedule(manifest)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out / "preflight.json", {
        key: value for key, value in preflight.items() if key != "prompts"
    })
    write_json_atomic(args.out / "prompts.json", preflight["prompts"])
    write_json_atomic(args.out / "schedule.json", schedule)
    if not args.execute:
        print(json.dumps({
            "status": "preflight_passed_not_executed", "provider_calls": 0,
            "planned_trajectories": len(schedule), "output_dir": str(args.out),
            "next_step": "Use --execute only when live execution is explicitly approved.",
        }, ensure_ascii=False, indent=2))
        return 0
    summary = asyncio.run(_run_live(args, manifest, args.out))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
