#!/usr/bin/env python3
"""Build and audit the four prompt variants for the paired-50 plan-influence screen.

This module is deliberately offline: it does not call a model or execute tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_user_messages(prepared: dict[str, Any], changed_tool: str, current_cost: float) -> dict[str, str]:
    old_plan = " -> ".join(prepared["incumbent_suffix"])
    current_types = ", ".join(sorted(prepared["state"]))
    prefix_name = prepared["prefix_name"] or "none"
    common = (
        prepared["user_request"]
        + "\n\n[Execution checkpoint]\n"
        + f"Previously completed prefix tool: {prefix_name}\n"
        + f"Prefix observation: {prepared['prefix_observation']}\n"
        + f"Current available data types: {current_types}\n"
    )
    plan_line = f"Existing remaining plan, selected before the environment update: {old_plan}\n"
    update_line = (
        "The tool environment has now changed. Continue the task from the current "
        "checkpoint using the currently available tools. "
    )
    localized = f"Current cost of {changed_tool}: {current_cost}.\n"
    choice_line = "Choose a feasible continuation from the current checkpoint. "
    tail = (
        "Make one tool call at a time. Do not merely state a decision; execute the task "
        f"until the goal type {prepared['goal_type']} is reached, then provide the final answer."
    )
    return {
        "A": common + plan_line + update_line + choice_line + tail,
        "B": common + plan_line + localized + update_line + choice_line + tail,
        "C": common + update_line + choice_line + tail,
        "D": common + localized + update_line + choice_line + tail,
    }


def validate_message_arms(messages: dict[str, str], changed_tool: str, current_cost: float) -> dict[str, Any]:
    if set(messages) != {"A", "B", "C", "D"}:
        raise ValueError("Expected exactly A/B/C/D prompt arms")
    if messages["A"] == messages["B"] or messages["C"] == messages["D"]:
        raise ValueError("Localized fact must change B and D")
    if "Existing remaining plan" not in messages["A"] or "Existing remaining plan" not in messages["B"]:
        raise ValueError("A/B must preserve incumbent plan")
    if "Existing remaining plan" in messages["C"] or "Existing remaining plan" in messages["D"]:
        raise ValueError("C/D must remove incumbent plan")
    fact = f"Current cost of {changed_tool}: {current_cost}."
    if fact not in messages["B"] or fact not in messages["D"]:
        raise ValueError("B/D must include exact current tool fact")
    if fact in messages["A"] or fact in messages["C"]:
        raise ValueError("A/C must not include localized fact")
    if "RETAIN" in fact or "SWITCH" in fact:
        raise ValueError("Fact sentence must not reveal condition label")
    return {
        "arms": ["A", "B", "C", "D"],
        "plan_visible": {"A": True, "B": True, "C": False, "D": False},
        "fact_localized": {"A": False, "B": True, "C": False, "D": True},
        "all_messages_nonempty": all(bool(v.strip()) for v in messages.values()),
    }


def main() -> None:
    manifest_path = Path(__file__).with_name("FOUR_ARM_TASK_MANIFEST.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["design"]["base_tasks"] != 8 or len(manifest["tasks"]) != 8:
        raise SystemExit("Frozen manifest must contain exactly eight base tasks")
    if len({row["query_id"] for row in manifest["tasks"]}) != 8:
        raise SystemExit("Duplicate task IDs in frozen manifest")
    if sum(bool(row["changed_tool_in_incumbent"]) for row in manifest["tasks"]) != 4:
        raise SystemExit("Expected four changed tools inside incumbent")
    if sum(not bool(row["changed_tool_in_incumbent"]) for row in manifest["tasks"]) != 4:
        raise SystemExit("Expected four changed tools outside incumbent")
    if len({row["category"] for row in manifest["tasks"]}) != 5:
        raise SystemExit("All five CostBench categories must be represented")
    print(json.dumps({"status": "manifest_valid", "tasks": 8, "provider_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
