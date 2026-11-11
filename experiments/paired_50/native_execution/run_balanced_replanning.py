#!/usr/bin/env python3
"""Compare two non-oracle plan-preserving replanning prompts at frozen checkpoints.

Dry run by default; --live explicitly authorizes billable model requests.
Reuses the CostBench native first-action execution and scoring path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path

import run_four_arm_experiment as benchmark
from four_arm_prompt_audit import build_user_messages

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "FOUR_ARM_TASK_MANIFEST.json"

COMPARISON_INSTRUCTION = (
    "\n\n[Decision check before the next tool call]\n"
    "The existing plan is a suggestion, not a requirement. At the current checkpoint, "
    "consider the current type state and tool dependencies. Identify feasible ways "
    "to reach the goal that start with the incumbent first action, and ways that start "
    "with a different action. Compare the full remaining continuations using the "
    "CURRENT tool definitions (not old assumptions), not just the immediate step. "
    "Keep the incumbent if no strictly better feasible continuation is supported "
    "by current evidence; otherwise take the first action of a better continuation. "
    "If evidence is insufficient to justify changing, retain the incumbent. "
    "Do not assume a change necessarily requires switching. "
    "Make exactly one native tool call as your next action; do not reply with a label."
)


def feasible_first_tools(prepared: dict) -> list[str]:
    """Only type-feasible names: no native solver, no gold labels, no oracle ranking."""
    state = set(prepared["state"])
    visible = {tool["function"]["name"] for tool in prepared["tool_interfaces"]}
    tools = [
        name for name, tool in prepared["tool_objects"].items()
        if name in visible and set(tool.input_types).issubset(state)
    ]
    return sorted(set(tools))


def build_balanced_payload(trial: dict, official_run) -> dict:
    prepared = trial["prepared"]
    arm = trial["prompt_condition"]
    if arm not in {"comparison", "feasible_menu"}:
        raise ValueError(f"Unknown plan-preserving intervention: {arm}")
    original = build_user_messages(
        prepared, prepared["changed_tool"],
        float(prepared["tool_objects"][prepared["changed_tool"]].cost),
    )["A"]
    if "Existing remaining plan" not in original:
        raise ValueError("The incumbent must remain visible in both conditions")
    prompt = original + COMPARISON_INSTRUCTION
    if arm == "feasible_menu":
        candidates = feasible_first_tools(prepared)
        incumbent = prepared["incumbent_suffix"][0]
        if incumbent not in candidates:
            raise ValueError(f"Incumbent not type-feasible: {incumbent}")
        prompt += (
            "\n\n[Non-oracle next-action feasibility list]\n"
            "These are all CURRENTLY type-feasible visible tool names, in alphabetical "
            "order, not ranked by quality. Some may fail to complete the goal and "
            "some may lead to inferior continuations. Use the full current tool "
            "definitions to decide. Feasible names: " + ", ".join(candidates)
        )
    prompt += "\nAct on the decision now using one available native tool call."
    system = benchmark.native.make_official_system_prompt(official_run, prepared["task"])
    return {
        "model": benchmark.native.MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "tools": prepared["tool_interfaces"],
        "temperature": 0,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
    }


def make_trials(selected, manifest, repetitions, seed):
    tasks = manifest["tasks"]
    if len(tasks) != 8:
        raise ValueError("Frozen eight-task manifest required")
    records = []
    for task in tasks:
        matches = [row for row in selected if row[0]["query_id"] == task["query_id"]]
        if len(matches) != 2:
            raise ValueError(f"Expected matched pair for {task['query_id']}")
        for task_row, request, manifest_row, prepared in matches:
            for arm in ("comparison", "feasible_menu"):
                for rep in range(1, repetitions + 1):
                    records.append({
                        "query_id": task["query_id"],
                        "category": task["category"],
                        "environment_condition": manifest_row["condition"],
                        "prompt_condition": arm,
                        "repetition": rep,
                        "trial_id": f"{task['query_id']}_{manifest_row['condition']}_{arm}_r{rep}",
                        "source_trial_id": request["trial_id"],
                        "task": task,
                        "request": request,
                        "manifest_row": manifest_row,
                        "prepared": prepared,
                    })
    random.Random(seed).shuffle(records)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--cap", type=int, default=1200000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--out", type=Path, default=HERE / "balanced_replanning_results")
    args = parser.parse_args()
    if args.repetitions != 2:
        raise ValueError("Primary protocol requires two frozen repetitions")
    args.costbench_root = args.costbench_root.resolve()
    args.out = args.out.resolve()
    data_dir = (HERE.parent / "generated").resolve()
    os.chdir(args.costbench_root)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cb = benchmark.native.load_costbench(args.costbench_root)
    if cb["revision"] != manifest["source"]["upstream_costbench_revision"]:
        raise ValueError("Upstream CostBench revision does not match frozen manifest")
    selected, _, _ = benchmark.load_selected_trials(data_dir, cb, manifest)
    trials = make_trials(selected, manifest, args.repetitions, args.seed)
    audit = benchmark.offline_audit(trials, cb["official_run"], args.max_tokens,
                                    payload_builder=build_balanced_payload)
    audit.update({
        "model": benchmark.native.MODEL,
        "method_arms": ["comparison", "feasible_menu"],
        "independent_base_tasks": 8,
        "environment_conditions": ["RETAIN", "SWITCH"],
        "not_a_heldout_test": True,
        "no_oracle_data_in_prompts": True,
    })
    if audit["trials_prepared"] != 64 or audit["unique_request_hashes"] != 32:
        # Two exact repetitions per arm share prompts; 8 x 2 x 2 unique payloads.
        raise ValueError("Unexpected trial count or prompt serialization")
    if not args.live:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("Missing DEEPSEEK_API_KEY; no paid requests sent")
    result = asyncio.run(benchmark.run_live(
        trials, cb["official_run"], args, payload_builder=build_balanced_payload
    ))
    result.update({
        "evidence_type": "development-cohort prompt intervention",
        "not_held_out": True,
        "oracle_assisted_prompt": False,
        "baseline_comparison": "frozen A arm, same 8 tasks, two repeats",
    })
    benchmark.save_json(args.out / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
