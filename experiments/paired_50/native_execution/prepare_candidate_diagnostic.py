#!/usr/bin/env python3
"""Prepare solver-audited candidate-diagnostic prompts; NEVER calls a model.

Requires the same pinned CostBench checkout and generated search-space data as
run_four_arm_experiment.py. Prints a concise summary or writes JSON on demand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path

import run_four_arm_experiment as screen

HERE = Path(__file__).resolve().parent
PRIMARY_SWITCH = {
    "Query00188", "Query00550", "Query00706",
    "Query00347", "Query00518", "Query00685", "Query00858",
}
PATH_LEVEL_ONLY = "Query00403"


def deterministic_orders(candidates: list[str], key: str) -> tuple[list[str], list[str]]:
    """Stable balanced candidate order; reverse is its exact counterpart."""
    order = sorted(set(candidates))
    random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)).shuffle(order)
    return order, list(reversed(order))


def make_prompt(prepared: dict, endpoint: str, menu: list[str] | None) -> str:
    base = screen.build_user_messages(
        prepared, prepared["changed_tool"],
        float(prepared["tool_objects"][prepared["changed_tool"]].cost),
    )["A"]
    if endpoint == "consideration":
        return (
            base.replace(
                "Make one tool call at a time. Do not merely state a decision; execute the task "
                f"until the goal type {prepared['goal_type']} is reached, then provide the final answer.",
                "For diagnostic analysis only, do not call any tool. Name up to three feasible "
                "next tools, including the incumbent action if feasible. Name a non-incumbent "
                "candidate if you can identify one. Return a JSON object with a 'candidates' "
                "array of exact tool names. Do not guess unavailable tools.",
            )
        )
    if endpoint not in {"comparison", "execution"} or not menu:
        raise ValueError("Comparison/execution requires an explicit candidate menu")
    suffix = (
        "For this diagnostic, choose only from the following currently feasible "
        "next tools (the list is not ranked): " + ", ".join(menu) + ". "
    )
    if endpoint == "comparison":
        suffix += (
            "Do not call any tool. Return a JSON object with a single 'chosen_tool' "
            "field containing the exact name you judge best under current tool values. "
            "The menu is supplied for evaluation only, not as an optimality hint."
        )
    else:
        suffix += (
            "Call exactly one of those tools now, using valid current-state arguments. "
            "Do not provide a label-only response."
        )
    original_tail = (
        "Make one tool call at a time. Do not merely state a decision; execute the task "
        f"until the goal type {prepared['goal_type']} is reached, then provide the final answer."
    )
    if original_tail not in base:
        raise ValueError("Cannot isolate original execution instruction")
    return base.replace(original_tail, "") + "\n\n[Diagnostic candidate menu]\n" + suffix


def prepare(costbench_root: Path, data_dir: Path) -> dict:
    os.chdir(costbench_root)
    source_manifest = json.loads((HERE / "FOUR_ARM_TASK_MANIFEST.json").read_text(encoding="utf-8"))
    costbench = screen.native.load_costbench(costbench_root)
    if costbench["revision"] != source_manifest["source"]["upstream_costbench_revision"]:
        raise ValueError("Pinned upstream revision differs from frozen manifest")
    selected, _, _ = screen.load_selected_trials(data_dir, costbench, source_manifest)
    rows = []
    prompt_rows = []
    for task, request, manifest, prepared in selected:
        env = manifest["condition"]
        query = task["query_id"]
        incumbent = prepared["incumbent_suffix"][0]
        optimum, values, oracle = screen.optimal_first_actions(prepared)
        eligible = env == "RETAIN" or query in PRIMARY_SWITCH
        if env == "SWITCH" and query == PATH_LEVEL_ONLY:
            if incumbent not in oracle:
                raise ValueError("Query00403 must remain first-action optimal")
            eligible = False
        if env == "SWITCH" and query in PRIMARY_SWITCH and incumbent in oracle:
            raise ValueError(f"Expected suboptimal incumbent in SWITCH: {query}")
        if incumbent not in values:
            raise ValueError(f"Infeasible incumbent action: {query}")
        available = {t["function"]["name"] for t in prepared["tool_interfaces"]}
        menu = sorted(set([incumbent] + oracle))
        if not set(menu).issubset(available):
            raise ValueError(f"Menu includes unavailable tool: {query}")
        for name in menu:
            tool = prepared["tool_objects"][name]
            if not set(tool.input_types).issubset(set(prepared["state"])):
                raise ValueError(f"Infeasible menu entry: {query}/{name}")
        rows.append({
            "query_id": query, "environment": env,
            "changed_tool_in_incumbent": task["changed_tool_in_incumbent"],
            "checkpoint_sha256": prepared["checkpoint_sha256"],
            "eligible_for_first_action": eligible,
            "incumbent": incumbent,
            "optimal_first_actions": oracle,
            "reference_optimum": optimum,
            "incumbent_first_action_value": values[incumbent],
            "candidate_menu": menu,
        })
        if not eligible:
            continue
        for endpoint in ("consideration", "comparison", "execution"):
            orders = [None] if endpoint == "consideration" else list(deterministic_orders(menu, query + "/" + env))
            for index, order in enumerate(orders):
                prompt = make_prompt(prepared, endpoint, order)
                # Reference choices are stored in a separate scoring manifest,
                # not inserted into any model-visible prompt.
                if "oracle_optimal" in prompt or "RETAIN/SWITCH" in prompt:
                    raise ValueError("Unexpected reference leakage in prompt")
                prompt_rows.append({
                    "query_id": query, "environment": env,
                    "endpoint": endpoint, "order": index if order is not None else None,
                    "checkpoint_sha256": prepared["checkpoint_sha256"],
                    "user_message": prompt, "menu": order,
                    "tools": prepared["tool_interfaces"],
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                })
    if len(rows) != 16 or sum(r["eligible_for_first_action"] for r in rows) != 15:
        raise ValueError("Expected 16 checkpoints and 15 eligible first-action cases")
    if len(prompt_rows) != 75:  # 15 x (1 consideration + 2 comparison + 2 execution)
        raise ValueError("Expected 75 offline prompt variants")
    return {
        "status": "offline_only_no_provider_calls",
        "upstream_revision": costbench["revision"],
        "checkpoint_count": len(rows),
        "eligible_first_action_checkpoints": 15,
        "path_level_exception": PATH_LEVEL_ONLY,
        "model_calls": 0,
        "prompt_variants": len(prompt_rows),
        "reference": rows,
        "prompts": prompt_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", required=True, type=Path)
    parser.add_argument("--data-dir", default=HERE.parent / "generated", type=Path)
    parser.add_argument("--out", type=Path, help="Optional output JSON path")
    args = parser.parse_args()
    result = prepare(args.costbench_root.resolve(), args.data_dir.resolve())
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "checkpoint_count": result["checkpoint_count"],
        "eligible_first_action_checkpoints": result["eligible_first_action_checkpoints"],
        "prompt_variants": result["prompt_variants"],
        "path_level_exception": result["path_level_exception"],
        "model_calls": result["model_calls"],
    }, indent=2))


if __name__ == "__main__":
    main()
