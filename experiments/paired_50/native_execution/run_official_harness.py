#!/usr/bin/env python3
"""Checkpointed native-tool execution for the frozen 50-task CostBench paired study.

This adapter reuses the pinned upstream CostBench tool registry, tool objects,
tool interfaces, prompt template, and _execute_tool_simulation helper. It adds
the fixed-checkpoint bootstrap required by the paired dataset. It makes no API
calls unless --live is supplied.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "generated"
UPSTREAM_SHA = "6424069f3f773ade076bcedbed302ed47cfb1837"
MODEL = "deepseek-flash"
REFINEMENT_LEVEL = 2
DEFAULT_TOKEN_CAP = 800_000
DEFAULT_MAX_TOOL_STEPS = 7
DEFAULT_MAX_TOKENS = 2048
RESERVATION_BUFFER = 512
ERROR_PREFIXES = ("[ERROR]", "Tool execution failed", "Error:")


def canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_resume_checkpoint(resume_dir: Path, requests, manifest, data_dir: Path):
    """Validate a prior run and return its complete prefix plus resumable final trace."""
    resume_dir = Path(resume_dir).resolve()
    responses_path = resume_dir / "responses.jsonl"
    ledger_path = resume_dir / "ledger.json"
    scores_path = resume_dir / "scores.json"
    if not all(path.is_file() for path in (responses_path, ledger_path, scores_path)):
        raise FileNotFoundError("Resume directory must contain responses.jsonl, ledger.json and scores.json.")

    previous_records = read_jsonl(responses_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    previous_scores = json.loads(scores_path.read_text(encoding="utf-8"))
    input_sha = sha_bytes((data_dir / "model_requests_100.jsonl").read_bytes())
    manifest_sha = sha_bytes((data_dir / "trial_manifest_100.json").read_bytes())

    if previous_scores.get("input_sha256") != input_sha:
        raise ValueError("Resume input hash does not match the current frozen requests.")
    if previous_scores.get("manifest_sha256") != manifest_sha:
        raise ValueError("Resume manifest hash does not match the current frozen manifest.")
    if previous_scores.get("status") != "incomplete" or ledger.get("status") != "incomplete":
        raise ValueError("Only an incomplete run can be resumed.")
    if ledger.get("planned_trials") != len(requests) or len(requests) != 100:
        raise ValueError("Resume checkpoint must belong to the full 100-trial cohort.")
    if len(previous_records) != ledger.get("attempted_trials"):
        raise ValueError("Resume record count does not match its ledger.")
    if not previous_records or len(previous_records) >= len(requests):
        raise ValueError("Resume checkpoint has no remaining trials.")

    for index, record in enumerate(previous_records):
        request = requests[index]
        manifest_row = manifest[request["trial_id"]]
        if record.get("trial_id") != request["trial_id"]:
            raise ValueError(f"Resume records are not a frozen-order prefix at index {index}.")
        if record.get("request_sha256") != canonical_sha(request):
            raise ValueError(f"Resume request hash mismatch at index {index}.")
        if record.get("checkpoint_sha256") != request["checkpoint_sha256"]:
            raise ValueError(f"Resume checkpoint hash mismatch at index {index}.")
        if record.get("condition") != manifest_row["condition"]:
            raise ValueError(f"Resume condition mismatch at index {index}.")

    for record in previous_records[:-1]:
        if record.get("halt_reason") != "goal_reached" or record.get("goal_state_reached") is not True:
            raise ValueError("Only fully completed trajectories may precede the resumable final trace.")

    partial = previous_records[-1]
    if partial.get("halt_reason") != "reservation_cap":
        raise ValueError("The final saved trajectory did not stop at the token reservation cap.")
    if not partial.get("trace") or int(partial.get("model_calls") or 0) <= 0:
        raise ValueError("The final saved trajectory has no executed trace to resume.")
    if partial.get("goal_state_reached") is True and partial.get("halt_reason") != "reservation_cap":
        raise ValueError("Unexpected completed goal state in the resume checkpoint.")

    charged = int(ledger.get("charged_tokens") or 0)
    reserved = int(ledger.get("reserved_tokens") or 0)
    observed_charged = sum(int(row.get("provider_total_tokens") or 0) for row in previous_records)
    if charged != observed_charged:
        raise ValueError("Resume ledger token total does not match the saved provider usage.")
    if charged != int(previous_scores.get("accounted_tokens") or 0):
        raise ValueError("Resume scores and ledger disagree on accounted tokens.")

    return {
        "completed_records": previous_records[:-1],
        "partial_record": partial,
        "resume_index": len(previous_records) - 1,
        "charged_tokens": charged,
        "reserved_tokens": reserved,
        "resume_dir": str(resume_dir),
    }


def load_frozen_inputs(data_dir: Path = DATA_DIR):
    requests = read_jsonl(data_dir / "model_requests_100.jsonl")
    manifest_doc = json.loads(
        (data_dir / "trial_manifest_100.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (data_dir / "task_registry_50.json").read_text(encoding="utf-8")
    )
    manifest_rows = manifest_doc.get("records", [])
    if len(requests) != 100 or len(manifest_rows) != 100:
        raise ValueError("The frozen paired dataset must contain 100 trials.")
    if registry.get("base_task_count") != 50:
        raise ValueError("The task registry must contain 50 base tasks.")
    if registry.get("upstream_revision") != UPSTREAM_SHA:
        raise ValueError("The task registry references a different CostBench revision.")

    manifest = {row["trial_id"]: row for row in manifest_rows}
    if len(manifest) != 100:
        raise ValueError("Duplicate trial IDs in the frozen manifest.")
    if len({row["trial_id"] for row in requests}) != 100:
        raise ValueError("Duplicate trial IDs in the frozen requests.")

    category_counts = Counter()
    condition_counts = Counter()
    grouped = defaultdict(list)
    task_ids = {
        row["task_id"]
        for row in registry.get("selection", {}).get("task_ids", [])
    }
    if len(task_ids) != 50:
        raise ValueError("The task registry must list 50 unique task IDs.")

    for index, request in enumerate(requests):
        trial_id = request["trial_id"]
        row = manifest.get(trial_id)
        if row is None or canonical_sha(request) != row["request_sha256"]:
            raise ValueError(f"Frozen request hash mismatch: {trial_id}")
        if request["query_id"] != row["query_id"]:
            raise ValueError(f"Task ID mismatch: {trial_id}")
        if request["checkpoint_sha256"] != row["checkpoint_sha256"]:
            raise ValueError(f"Checkpoint hash mismatch: {trial_id}")
        if set(request) != {
            "trial_id", "query_id", "checkpoint_sha256", "messages", "response_format"
        }:
            raise ValueError(f"Unexpected request fields: {trial_id}")
        if request["response_format"] != {"type": "json_object"}:
            raise ValueError(f"Unexpected response format: {trial_id}")
        if [message["role"] for message in request["messages"]] != ["system", "user"]:
            raise ValueError(f"Unexpected frozen message structure: {trial_id}")

        visible = json.loads(request["messages"][-1]["content"])
        if any(
            key in visible
            for key in ("condition", "oracle_cost", "regret", "gold_label", "correct_answer")
        ):
            raise ValueError(f"Gold information appears in model-visible input: {trial_id}")
        required_visible = {
            "task_id", "task", "user_request", "available_types",
            "goal_type", "supplied_old_plan_suffix", "current_tools"
        }
        if set(visible) != required_visible:
            raise ValueError(f"Unexpected model-visible fields: {trial_id}")
        if visible["task_id"] != request["query_id"]:
            raise ValueError(f"Visible task ID mismatch: {trial_id}")
        if request["query_id"] not in task_ids:
            raise ValueError(f"Task is absent from the 50-task registry: {trial_id}")

        condition_counts[row["condition"]] += 1
        grouped[request["query_id"]].append((request, row, visible))
        if index % 2 == 0 and index + 1 < len(requests):
            if requests[index + 1]["query_id"] != request["query_id"]:
                raise ValueError("Paired trials must remain adjacent in the frozen order.")

    if condition_counts != {"RETAIN": 50, "SWITCH": 50}:
        raise ValueError(f"Condition balance mismatch: {dict(condition_counts)}")
    if set(grouped) != task_ids or len(grouped) != 50:
        raise ValueError("The requests and task registry do not contain the same 50 tasks.")

    for query_id, rows in grouped.items():
        if len(rows) != 2 or {row[1]["condition"] for row in rows} != {"RETAIN", "SWITCH"}:
            raise ValueError(f"Unpaired conditions for {query_id}.")
        if len({row[0]["checkpoint_sha256"] for row in rows}) != 1:
            raise ValueError(f"Paired checkpoint mismatch for {query_id}.")
        if rows[0][2]["supplied_old_plan_suffix"] != rows[1][2]["supplied_old_plan_suffix"]:
            raise ValueError(f"Paired incumbent suffix mismatch for {query_id}.")

    return requests, manifest, registry


def relevant_tool_names(tool_defs: dict[str, dict[str, Any]], state: set[str], goal: str):
    """Match the cost-independent reachability filter used by the dataset builder."""
    reachable = set(state)
    changed = True
    while changed:
        changed = False
        for tool in tool_defs.values():
            if set(tool["input_types"]).issubset(reachable):
                if tool["output_type"] not in reachable:
                    reachable.add(tool["output_type"])
                    changed = True

    if goal not in reachable:
        raise ValueError(f"Goal type is unreachable from checkpoint: {goal}")

    backward = {goal}
    changed = True
    while changed:
        changed = False
        for tool in tool_defs.values():
            if (
                tool["output_type"] in backward
                and set(tool["input_types"]).issubset(reachable)
            ):
                for input_type in tool["input_types"]:
                    if input_type not in backward:
                        backward.add(input_type)
                        changed = True

    return {
        name
        for name, tool in tool_defs.items()
        if tool["output_type"] in backward
        and set(tool["input_types"]).issubset(reachable)
    }


def walk_type_state(state: set[str], path: list[str], tool_defs: dict[str, dict[str, Any]]):
    current = set(state)
    for name in path:
        if name not in tool_defs:
            raise ValueError(f"Plan references unavailable tool: {name}")
        tool = tool_defs[name]
        missing = set(tool["input_types"]) - current
        if missing:
            raise ValueError(f"Plan is not type-feasible at {name}; missing {sorted(missing)}")
        current.add(tool["output_type"])
    return current


def query_input_for_type(input_type: str, query: dict[str, Any], task: str) -> str:
    if input_type == "LocationPreference":
        value = query.get("location_preference")
    elif input_type == "TimeInfo":
        value = query.get("TimeInfo")
    else:
        task_prefix = task.capitalize()
        suffix_to_key = {
            "Category": "category",
            "Tier": "tier",
            "Style": "style",
            "FeaturePackage": "feature_package",
        }
        value = None
        for suffix, key in suffix_to_key.items():
            if input_type == task_prefix + suffix:
                value = query.get("preferences", {}).get(key)
                break
    if not isinstance(value, str) or not value:
        raise ValueError(f"Cannot reconstruct prefix input {input_type} from the source query.")
    return value


def build_prefix_arguments(prefix_tool, query: dict[str, Any], task: str):
    return {
        input_type: query_input_for_type(input_type, query, task)
        for input_type in prefix_tool.input_types
    }


def load_costbench(root: Path):
    root = root.resolve()
    if not (root / "env" / "run.py").is_file():
        raise FileNotFoundError(f"CostBench checkout not found at {root}")
    try:
        revision_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("CostBench checkout must be a Git repository at the pinned revision.") from exc
    revision = revision_result.stdout.strip()
    if revision != UPSTREAM_SHA:
        raise ValueError(
            f"CostBench revision mismatch: expected {UPSTREAM_SHA}, got {revision}"
        )
    sys.path.insert(0, str(root))
    import env.run as official_run
    from env.core.base_types import create_tool_from_dict
    from env.domains.travel.tool_registry import tools_ready_in_memory
    from env.utils.solver import GroundtruthSolver

    return {
        "root": root,
        "revision": revision or UPSTREAM_SHA,
        "official_run": official_run,
        "create_tool_from_dict": create_tool_from_dict,
        "tools_ready_in_memory": tools_ready_in_memory,
        "GroundtruthSolver": GroundtruthSolver,
    }


def make_tool_objects(tool_defs, create_tool_from_dict):
    return {
        name: create_tool_from_dict({**definition, "name": name})
        for name, definition in tool_defs.items()
    }


def execute_prefix(prefix_tool, arguments, available_tools, refinement_level: int):
    """Replay the already-completed prefix with native CostBench tool code."""
    input_data = prefix_tool.process_input(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    )
    if isinstance(input_data, dict) and "error_message" in input_data:
        raise RuntimeError(input_data["error_message"])
    output = prefix_tool.execute(
        input_data=input_data,
        available_tools=available_tools,
    )
    if output is None or (
        isinstance(output, str) and output.startswith(ERROR_PREFIXES)
    ):
        raise RuntimeError(f"Prefix tool failed: {output}")
    observation = prefix_tool.process_output(
        tool_output=output,
        refinement_level=refinement_level,
        available_tools=available_tools,
    )
    if not isinstance(observation, str) or observation.startswith(ERROR_PREFIXES):
        raise RuntimeError(f"Prefix observation failed: {observation}")
    if "Cost:" not in observation and prefix_tool.has_cost():
        observation += f" Cost: {prefix_tool.cost}"
    return output, observation


def prepare_trial(request, manifest_row, query, registry_row, costbench):
    visible = json.loads(request["messages"][-1]["content"])
    task = visible["task"]
    goal = visible["goal_type"]
    query_id = request["query_id"]
    numeric_id = int(query_id.removeprefix("Query"))
    seed = 200000 + numeric_id

    snapshot = costbench["tools_ready_in_memory"](
        refinement_level=REFINEMENT_LEVEL,
        random_seed=seed,
        ban_longest_tool=True,
    )
    raw_tools = snapshot["tools"]
    if not raw_tools:
        raise ValueError(f"Empty native tool registry for {query_id}")

    create_tool = costbench["create_tool_from_dict"]
    all_tool_objects = make_tool_objects(raw_tools, create_tool)
    initial_solver = costbench["GroundtruthSolver"](all_tool_objects)
    initial_state = set(initial_solver._infer_initial_state(task))
    initial_path = initial_solver.solve(
        current_state=initial_state,
        goal_types={goal},
    ).tools

    # This reproduces the frozen fixture rule: execute the first optimal tool
    # only when the original optimal path contains at least two tools.
    prefix = initial_path[:1] if len(initial_path) >= 2 else []
    state = set(initial_state)
    prefix_observation = "No prefix tool was required; execution starts at the recorded initial state."
    prefix_output_id = None
    prefix_name = None

    task_tool_defs = {
        name: definition
        for name, definition in raw_tools.items()
        if task.capitalize() in name
    }
    task_tool_objects = {
        name: all_tool_objects[name]
        for name in task_tool_defs
    }

    if prefix:
        prefix_name = prefix[0]
        if prefix_name not in task_tool_objects:
            raise ValueError(f"Frozen prefix tool is absent from native registry: {prefix_name}")
        prefix_tool = task_tool_objects[prefix_name]
        prefix_args = build_prefix_arguments(prefix_tool, query, task)
        prefix_output, prefix_observation = execute_prefix(
            prefix_tool,
            prefix_args,
            task_tool_objects,
            REFINEMENT_LEVEL,
        )
        if type(prefix_output).__name__ != prefix_tool.output_type:
            raise ValueError(
                f"Prefix output type mismatch for {query_id}: "
                f"{type(prefix_output).__name__} != {prefix_tool.output_type}"
            )
        prefix_output_id = getattr(prefix_output, "unique_id", None)
        expected_preference_id = query.get("groundtruth")
        if expected_preference_id and prefix_output_id != expected_preference_id:
            raise ValueError(
                f"Prefix replay ID mismatch for {query_id}: "
                f"{prefix_output_id} != {expected_preference_id}"
            )
        state.add(prefix_tool.output_type)

    checkpoint = {
        "types": sorted(state),
        "prefix": prefix,
        "source": "oracle_derived_type_state",
        "query_id": query_id,
        "task": task,
    }
    checkpoint_hash = canonical_sha(checkpoint)
    if checkpoint_hash != request["checkpoint_sha256"]:
        raise ValueError(f"Reconstructed checkpoint hash mismatch for {query_id}")
    if checkpoint_hash != registry_row["checkpoint_sha256"]:
        raise ValueError(f"Task registry checkpoint mismatch for {query_id}")
    if sorted(state) != visible["available_types"]:
        raise ValueError(f"Reconstructed state differs from frozen request for {query_id}")

    current_meta = visible["current_tools"]
    expected_visible_names = relevant_tool_names(raw_tools, state, goal)
    if set(current_meta) != expected_visible_names:
        missing = sorted(expected_visible_names - set(current_meta))
        extra = sorted(set(current_meta) - expected_visible_names)
        raise ValueError(
            f"Visible tool set mismatch for {query_id}; missing={missing}, extra={extra}"
        )

    changed_tools = []
    current_tool_defs = {}
    for name, metadata in current_meta.items():
        if name not in raw_tools:
            raise ValueError(f"Frozen request references unknown native tool {name}")
        baseline = raw_tools[name]
        if (
            list(baseline["input_types"]) != metadata["input_types"]
            or baseline["output_type"] != metadata["output_type"]
        ):
            raise ValueError(f"Native tool schema mismatch for {query_id}: {name}")
        current_definition = dict(baseline)
        current_definition["cost"] = metadata["cost"]
        current_tool_defs[name] = current_definition
        if abs(float(metadata["cost"]) - float(baseline["cost"])) > 1e-9:
            changed_tools.append(name)

    if len(changed_tools) != 1:
        raise ValueError(
            f"Expected exactly one changed tool in {query_id}; found {changed_tools}"
        )
    changed_tool = changed_tools[0]
    if changed_tool in prefix:
        raise ValueError(f"The frozen environment change alters the executed prefix for {query_id}")

    for name, definition in current_tool_defs.items():
        if definition.get("type") == "composite":
            missing_components = [
                component
                for component in definition.get("component_tool_names", [])
                if component not in current_tool_defs
            ]
            if missing_components:
                raise ValueError(
                    f"Visible composite {name} lacks component tools: {missing_components}"
                )

    incumbent_suffix = visible["supplied_old_plan_suffix"]
    final_old_state = walk_type_state(state, incumbent_suffix, current_tool_defs)
    if goal not in final_old_state:
        raise ValueError(f"Incumbent suffix does not reach the goal for {query_id}")

    current_tool_objects = make_tool_objects(current_tool_defs, create_tool)
    condition_solver = costbench["GroundtruthSolver"](current_tool_objects)
    optimum = condition_solver.solve(
        current_state=state,
        goal_types={goal},
    )
    incumbent_value = sum(
        float(current_tool_defs[name]["cost"]) for name in incumbent_suffix
    )
    regret = incumbent_value - float(optimum.total_cost)
    condition = manifest_row["condition"]
    if condition == "RETAIN" and abs(regret) > 1e-6:
        raise ValueError(f"RETAIN fixture failed native oracle audit for {query_id}")
    if condition == "SWITCH" and regret < 1.0 - 1e-6:
        raise ValueError(f"SWITCH fixture failed native oracle audit for {query_id}")

    tool_interfaces = [
        current_tool_objects[name].generate_interface(provide_composite_concept=False)
        for name in sorted(current_tool_objects)
    ]
    return {
        "trial_id": request["trial_id"],
        "query_id": query_id,
        "condition": condition,
        "task": task,
        "goal_type": goal,
        "state": state,
        "checkpoint_sha256": checkpoint_hash,
        "prefix": prefix,
        "prefix_name": prefix_name,
        "prefix_observation": prefix_observation,
        "prefix_output_id": prefix_output_id,
        "incumbent_suffix": incumbent_suffix,
        "changed_tool": changed_tool,
        "native_optimal_path": list(optimum.tools),
        "native_regret_audit": round(regret, 6),
        "tool_objects": current_tool_objects,
        "tool_interfaces": tool_interfaces,
        "user_request": visible["user_request"],
    }


def audit_prepared_pairs(prepared_rows):
    grouped = defaultdict(list)
    for row in prepared_rows:
        grouped[row["query_id"]].append(row)
    if len(grouped) != 50:
        raise ValueError(f"Expected 50 prepared base tasks, got {len(grouped)}")
    for query_id, rows in grouped.items():
        if len(rows) != 2 or {row["condition"] for row in rows} != {"RETAIN", "SWITCH"}:
            raise ValueError(f"Missing paired execution condition for {query_id}")
        for field in ("checkpoint_sha256", "prefix", "incumbent_suffix", "changed_tool"):
            if rows[0][field] != rows[1][field]:
                raise ValueError(f"Paired {field} mismatch for {query_id}")
        if set(rows[0]["tool_objects"]) != set(rows[1]["tool_objects"]):
            raise ValueError(f"Paired visible tool set mismatch for {query_id}")
    return {
        "base_tasks": len(grouped),
        "trials": len(prepared_rows),
        "conditions": dict(Counter(row["condition"] for row in prepared_rows)),
        "category_counts": dict(Counter(row["task"] for row in grouped.values() for row in row[:1])),
        "prefix_tool_count": sum(bool(row["prefix"]) for row in grouped.values() for row in row[:1]),
        "unique_changed_tools": len({row["changed_tool"] for row in prepared_rows}),
    }


def make_official_system_prompt(official_run, task: str):
    args = SimpleNamespace(
        refinement_level=REFINEMENT_LEVEL,
        provide_atomic_tool_sequence=False,
        provide_composite_concept=False,
    )
    refinement_content = official_run.REFINEMENT_CONTENT_TEMPLATE.format(
        task=task.capitalize(),
        num_dimensions=REFINEMENT_LEVEL,
        refinement_dimensions_str=official_run.get_refinement_dimensions_str(args),
    )
    return official_run.QUERY_INSTRUCTION.format(
        task=task.capitalize(),
        tool_num_str=official_run.get_tool_num_str(args),
        tool_types_str=official_run.get_tool_types_str(args),
        refinement_content=refinement_content,
        example_content="",
        composite_concept_content="",
        task_atomic_tool_sequence_str="",
        need_loc_pref="LocationPreference, " if task.lower() != "location" else "",
    )


def make_checkpoint_user_message(prepared):
    old_plan = " -> ".join(prepared["incumbent_suffix"])
    current_types = ", ".join(sorted(prepared["state"]))
    prefix_name = prepared["prefix_name"] or "none"
    return (
        prepared["user_request"]
        + "\n\n[Execution checkpoint]\n"
        + f"Previously completed prefix tool: {prefix_name}\n"
        + f"Prefix observation: {prepared['prefix_observation']}\n"
        + f"Current available data types: {current_types}\n"
        + f"Existing remaining plan, selected before the environment update: {old_plan}\n"
        + "The tool environment has now changed. Continue the task from the current "
        + "checkpoint using the currently available tools. You may continue the "
        + "existing plan or choose a different feasible continuation. Make one "
        + "tool call at a time. Do not merely state a decision; execute the task "
        + f"until the goal type {prepared['goal_type']} is reached, then provide "
        + "the final answer."
    )


def reservation_for_call(messages, tool_interfaces, max_tokens: int) -> int:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tool_interfaces,
        "temperature": 0,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
    }
    return (
        len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        + max_tokens
        + RESERVATION_BUFFER
    )


def classify_first_action(executed_path: list[str], incumbent_suffix: list[str]):
    if not executed_path:
        return None
    return "RETAIN" if executed_path[0] == incumbent_suffix[0] else "SWITCH"


def trajectory_relation(executed_path: list[str], incumbent_suffix: list[str]):
    if not executed_path:
        return "no_tool_action"
    if executed_path == incumbent_suffix:
        return "exact_incumbent_suffix"
    if incumbent_suffix[: len(executed_path)] == executed_path:
        return "incumbent_prefix"
    if executed_path[0] == incumbent_suffix[0]:
        return "started_incumbent_then_diverged"
    return "alternative_continuation"


def grade_execution(records, manifest, planned_trials: int = 100):
    seen = {}
    for record in records:
        trial_id = record.get("trial_id")
        if trial_id not in manifest or trial_id in seen:
            raise ValueError("Unknown or duplicated execution record.")
        if record.get("request_sha256") != manifest[trial_id]["request_sha256"]:
            raise ValueError(f"Execution record hash mismatch: {trial_id}")
        seen[trial_id] = record

    by_condition = {
        "RETAIN": Counter(),
        "SWITCH": Counter(),
    }
    pairs = defaultdict(dict)
    relation_counts = Counter()
    goal_reached = 0
    for trial_id, manifest_row in manifest.items():
        record = seen.get(trial_id)
        if record is None:
            continue
        truth = manifest_row["condition"]
        prediction = record.get("first_action_prediction")
        by_condition[truth]["total"] += 1
        if prediction is None:
            by_condition[truth]["no_first_action"] += 1
        elif prediction == "RETAIN":
            by_condition[truth]["followed_incumbent"] += 1
        elif prediction == "SWITCH":
            by_condition[truth]["departed_incumbent"] += 1
        else:
            by_condition[truth]["invalid_prediction"] += 1
        pairs[manifest_row["query_id"]][truth] = prediction
        relation_counts[record.get("trajectory_relation", "unknown")] += 1
        goal_reached += int(record.get("goal_state_reached") is True)

    if planned_trials <= 0 or planned_trials > 100:
        raise ValueError("planned_trials must be between 1 and 100.")
    complete = len(seen) == planned_trials
    cohort_complete = len(seen) == 100
    paired_tasks_attempted = sum(len(values) == 2 for values in pairs.values())
    pair_outcomes = Counter()
    for values in pairs.values():
        if len(values) == 2:
            pair_outcomes[f'{values.get("RETAIN")}/{values.get("SWITCH")}'] += 1
    switch_rows = by_condition["SWITCH"]
    retain_rows = by_condition["RETAIN"]
    return {
        "status": "complete" if complete else "incomplete",
        "attempted_trials": len(seen),
        "planned_trials": planned_trials,
        "total_trials": 100,
        "cohort_complete": cohort_complete,
        "cohort_coverage": len(seen) / 100,
        "base_tasks": 50,
        "retain_condition_first_action_behavior": dict(retain_rows),
        "switch_condition_first_action_behavior": dict(switch_rows),
        "paired_tasks_attempted": paired_tasks_attempted,
        "paired_task_coverage": paired_tasks_attempted / 50,
        "paired_first_action_behavior": dict(pair_outcomes),
        "first_action_followed_incumbent": sum(
            row["followed_incumbent"] for row in by_condition.values()
        ),
        "first_action_departed_incumbent": sum(
            row["departed_incumbent"] for row in by_condition.values()
        ),
        "goal_state_reached": goal_reached,
        "goal_state_rate": goal_reached / len(seen) if seen else None,
        "trajectory_relations": dict(relation_counts),
        "api_error_trials": sum(
            str(row.get("halt_reason", "")).startswith("api_error:")
            for row in seen.values()
        ),
        "runner_error_trials": sum(
            row.get("halt_reason") == "runner_exception"
            for row in seen.values()
        ),
        "reservation_limited_trials": sum(
            row.get("halt_reason") == "reservation_cap"
            for row in seen.values()
        ),
        "provider_total_tokens": sum(
            int(row.get("provider_total_tokens") or 0) for row in seen.values()
        ),
        "interpretation": (
            "First-action behavior is descriptive: RETAIN means the first executed "
            "tool equals the incumbent's first tool; SWITCH means it differs. "
            "Neither label alone establishes current-condition optimality."
        ),
    }



class TokenBudget:
    def __init__(self, cap: int, charged: int = 0, reserved: int = 0):
        if cap <= 0 or charged < 0 or reserved < 0 or charged > cap:
            raise ValueError("Invalid token budget initialization.")
        self.cap = cap
        self.charged = charged
        self.reserved = reserved

    def can_call(self, reserve: int) -> bool:
        return self.charged + reserve <= self.cap

    def record_usage(self, usage: Any):
        total = getattr(usage, "total_tokens", None)
        if not isinstance(total, int):
            raise RuntimeError("Provider response did not include total_tokens usage.")
        self.charged += total
        return total


async def call_model(client, messages, tool_interfaces, tool_choice, max_tokens, budget):
    reserve = reservation_for_call(messages, tool_interfaces, max_tokens)
    if not budget.can_call(reserve):
        raise RuntimeError("reservation_cap")
    budget.reserved += reserve
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        max_tokens=max_tokens,
        tools=tool_interfaces,
        tool_choice=tool_choice,
        parallel_tool_calls=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
    if not response.choices:
        raise RuntimeError("empty_model_choices")
    budget.record_usage(response.usage)
    if budget.charged > budget.cap:
        raise RuntimeError("usage_exceeded_cap")
    return response


def assistant_message_dict(message):
    tool_calls = []
    for call in message.tool_calls or []:
        tool_calls.append({
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            },
        })
    return {
        "role": "assistant",
        "content": message.content,
        **({"tool_calls": tool_calls} if tool_calls else {}),
    }


def restore_partial_execution(prepared, record, messages):
    """Rebuild the native tool-call context from a saved, already executed trace."""
    state = set(prepared["state"])
    tool_objects = prepared["tool_objects"]
    executed_path = []
    trace = []
    for index, item in enumerate(record.get("trace", []), 1):
        tool_name = item.get("tool_name")
        tool_obj = tool_objects.get(tool_name)
        if tool_obj is None:
            raise ValueError(f"Cannot resume unknown native tool: {tool_name}")
        missing = set(tool_obj.input_types) - state
        if missing:
            raise ValueError(
                f"Saved trace is not type-feasible at {tool_name}: {sorted(missing)}"
            )
        call_id = f"resume_call_{index}"
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": item["arguments"],
                },
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": str(item.get("output", "")),
        })
        if item.get("success") is True:
            state.add(tool_obj.output_type)
        executed_path.append(tool_name)
        trace.append(dict(item))

    if not trace:
        raise ValueError("Cannot resume a trajectory without an executed tool trace.")
    if executed_path != record.get("executed_path"):
        raise ValueError("Saved trace and executed_path disagree.")
    if record.get("final_state_types") != sorted(state):
        raise ValueError("Saved final state does not match replayed native tool outputs.")
    if record.get("first_action") != executed_path[0]:
        raise ValueError("Saved first action does not match the resumed trace.")
    return state, executed_path, trace


async def execute_trial(
    prepared, request, manifest_row, official_run, client, args, budget,
    resume_record=None,
):
    messages = [
        {"role": "system", "content": make_official_system_prompt(official_run, prepared["task"])},
        {"role": "user", "content": make_checkpoint_user_message(prepared)},
    ]
    state = set(prepared["state"])
    tool_objects = prepared["tool_objects"]
    tool_interfaces = prepared["tool_interfaces"]
    executed_path = []
    trace = []
    model_calls = 0
    trial_tokens = 0
    halt_reason = None
    final_text = None
    reported_model = None
    start_step = 1
    resumed_from_partial = resume_record is not None

    if resume_record is not None:
        if resume_record.get("trial_id") != request["trial_id"]:
            raise ValueError("Partial resume record does not match the current frozen trial.")
        if resume_record.get("checkpoint_sha256") != prepared["checkpoint_sha256"]:
            raise ValueError("Partial resume checkpoint hash mismatch.")
        state, executed_path, trace = restore_partial_execution(
            prepared, resume_record, messages
        )
        model_calls = int(resume_record.get("model_calls") or 0)
        trial_tokens = int(resume_record.get("provider_total_tokens") or 0)
        reported_model = resume_record.get("model_reported")
        final_text = resume_record.get("final_text")
        start_step = len(trace) + 1

    for step in range(start_step, args.max_tool_steps + 1):
        try:
            response = await call_model(
                client, messages, tool_interfaces,
                "required" if prepared["goal_type"] not in state else "none",
                args.max_tokens, budget,
            )
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            halt_reason = reason if reason == "reservation_cap" else "api_error:" + reason
            break

        model_calls += 1
        trial_tokens += int(response.usage.total_tokens)
        reported_model = getattr(response, "model", None) or reported_model
        choice = response.choices[0]
        message = choice.message
        messages.append(assistant_message_dict(message))
        tool_calls = message.tool_calls or []

        if not tool_calls:
            final_text = message.content
            if prepared["goal_type"] in state:
                halt_reason = "goal_reached_text_response"
            else:
                halt_reason = "premature_text_response"
            break

        tool_call = tool_calls[0]
        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments
        tool_obj = tool_objects.get(tool_name)
        if tool_obj is None:
            tool_result = f"[ERROR] Invalid tool '{tool_name}' for this checkpoint."
            success = False
        else:
            missing = set(tool_obj.input_types) - state
            if missing:
                tool_result = (
                    f"[ERROR] Missing required input types for '{tool_name}': "
                    f"{sorted(missing)}. Current state: {sorted(state)}"
                )
                success = False
            else:
                try:
                    tool_result = official_run._execute_tool_simulation(
                        tool_obj=tool_obj,
                        arguments_str=arguments,
                        refinement_level=REFINEMENT_LEVEL,
                        available_tools=tool_objects,
                    )
                    success = not (
                        isinstance(tool_result, str)
                        and tool_result.startswith(ERROR_PREFIXES)
                    )
                except Exception as exc:
                    tool_result = f"[ERROR] Error executing tool: {type(exc).__name__}: {exc}"
                    success = False

        executed_path.append(tool_name)
        trace.append({
            "step": step,
            "tool_name": tool_name,
            "tool_cost": getattr(tool_obj, "cost", None) if tool_obj else None,
            "arguments": arguments,
            "success": success,
            "output": tool_result,
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": str(tool_result),
        })

        if len(tool_calls) > 1:
            for extra in tool_calls[1:]:
                messages.append({
                    "role": "tool",
                    "tool_call_id": extra.id,
                    "name": extra.function.name,
                    "content": (
                        "[ERROR] Multiple tool calls in one step are not allowed. "
                        "Only the first tool call was executed."
                    ),
                })

        if success and tool_obj is not None:
            state.add(tool_obj.output_type)

        if prepared["goal_type"] in state:
            try:
                final_response = await call_model(
                    client, messages, tool_interfaces, "none", args.max_tokens, budget
                )
                model_calls += 1
                trial_tokens += int(final_response.usage.total_tokens)
                reported_model = getattr(final_response, "model", None) or reported_model
                final_message = final_response.choices[0].message
                messages.append(assistant_message_dict(final_message))
                final_text = final_message.content
                halt_reason = "goal_reached"
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                halt_reason = reason if reason == "reservation_cap" else "api_error:" + reason
            break
    else:
        halt_reason = "max_tool_steps"

    prediction = classify_first_action(executed_path, prepared["incumbent_suffix"])
    oracle_path = prepared["native_optimal_path"]
    oracle_first_action = oracle_path[0] if oracle_path else None
    record = {
        "trial_id": request["trial_id"],
        "query_id": request["query_id"],
        "request_sha256": canonical_sha(request),
        "checkpoint_sha256": prepared["checkpoint_sha256"],
        "condition": manifest_row["condition"],
        "model_requested": MODEL,
        "model_reported": reported_model,
        "resumed_from_partial": resumed_from_partial,
        "first_action_prediction": prediction,
        "first_action_is_incumbent": prediction == "RETAIN" if prediction is not None else None,
        "oracle_first_action": oracle_first_action,
        "first_action_success": trace[0]["success"] if trace else None,
        "first_action": executed_path[0] if executed_path else None,
        "incumbent_first_action": prepared["incumbent_suffix"][0],
        "executed_path": executed_path,
        "trajectory_relation": trajectory_relation(
            executed_path, prepared["incumbent_suffix"]
        ),
        "goal_state_reached": prepared["goal_type"] in state,
        "final_state_types": sorted(state),
        "final_text": final_text,
        "halt_reason": halt_reason,
        "model_calls": model_calls,
        "provider_total_tokens": trial_tokens,
        "trace": trace,
        "prefix": prepared["prefix"],
        "prefix_observation": prepared["prefix_observation"],
        "changed_tool": prepared["changed_tool"],
        "native_optimal_path_audit": prepared["native_optimal_path"],
        "native_regret_audit": prepared["native_regret_audit"],
    }
    return record


def save_json(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


async def run_live(prepared_rows, requests, manifest, costbench, args):
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is unavailable; no API call was made.")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"Output directory is nonempty: {args.out}")

    prior_records = []
    resume_record = None
    resume_index = 0
    initial_charged = 0
    initial_reserved = 0
    resume_metadata = None
    if args.resume_from is not None:
        if len(requests) != 100 or len(prepared_rows) != 100 or args.trial_ids:
            raise ValueError("Resume is supported only for the complete frozen 100-trial cohort.")
        resume_metadata = load_resume_checkpoint(
            args.resume_from, requests, manifest, args.data_dir
        )
        prior_records = resume_metadata["completed_records"]
        resume_record = resume_metadata["partial_record"]
        resume_index = resume_metadata["resume_index"]
        initial_charged = resume_metadata["charged_tokens"]
        initial_reserved = resume_metadata["reserved_tokens"]

    args.out.mkdir(parents=True, exist_ok=True)
    official_run = costbench["official_run"]
    client = official_run.AsyncOpenAI(
        base_url="https://api.deepseek.com",
        api_key=key,
        timeout=args.timeout,
    )
    budget = TokenBudget(
        args.cap, charged=initial_charged, reserved=initial_reserved
    )
    records = list(prior_records)
    response_path = args.out / "responses.jsonl"
    if records:
        with response_path.open("w", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    try:
        for index in range(resume_index, len(requests)):
            prepared = prepared_rows[index]
            request = requests[index]
            row = manifest[request["trial_id"]]
            start = time.monotonic()
            current_resume = resume_record if index == resume_index else None
            try:
                record = await execute_trial(
                    prepared, request, row, official_run, client, args, budget,
                    resume_record=current_resume,
                )
            except Exception as exc:
                record = {
                    "trial_id": request["trial_id"],
                    "query_id": request["query_id"],
                    "request_sha256": canonical_sha(request),
                    "checkpoint_sha256": prepared["checkpoint_sha256"],
                    "condition": row["condition"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "halt_reason": "runner_exception",
                    "provider_total_tokens": 0,
                    "executed_path": [],
                    "first_action_prediction": None,
                    "goal_state_reached": False,
                }
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record["accounted_tokens_after_trial"] = budget.charged
            records.append(record)

            with response_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            save_json(args.out / "ledger.json", {
                "status": "in_progress",
                "attempted_trials": len(records),
                "planned_trials": len(requests),
                "charged_tokens": budget.charged,
                "reserved_tokens": budget.reserved,
                "token_cap": budget.cap,
                "input_sha256": sha_bytes(
                    (args.data_dir / "model_requests_100.jsonl").read_bytes()
                ),
                "manifest_sha256": sha_bytes(
                    (args.data_dir / "trial_manifest_100.json").read_bytes()
                ),
                "resumed_from": resume_metadata["resume_dir"] if resume_metadata else None,
                "resumed_partial_trial_id": resume_record.get("trial_id") if resume_record else None,
                "initial_charged_tokens": initial_charged,
                "no_retries": True,
            })
            print(json.dumps({
                "trial": index + 1,
                "query_id": request["query_id"],
                "condition": row["condition"],
                "first_action_prediction": record.get("first_action_prediction"),
                "goal_state_reached": record.get("goal_state_reached"),
                "halt_reason": record.get("halt_reason"),
                "resumed_from_partial": record.get("resumed_from_partial", False),
                "charged_tokens": budget.charged,
            }), flush=True)

            if record.get("halt_reason") in {"reservation_cap", "usage_exceeded_cap"}:
                break
            if record.get("halt_reason") and record["halt_reason"].startswith("api_error:"):
                break
            if record.get("halt_reason") == "runner_exception":
                break

    finally:
        await client.close()

    scores = grade_execution(records, manifest, planned_trials=len(requests))
    scores.update({
        "token_cap": budget.cap,
        "accounted_tokens": budget.charged,
        "reserved_tokens": budget.reserved,
        "input_sha256": sha_bytes(
            (args.data_dir / "model_requests_100.jsonl").read_bytes()
        ),
        "manifest_sha256": sha_bytes(
            (args.data_dir / "trial_manifest_100.json").read_bytes()
        ),
        "resumed_from": resume_metadata["resume_dir"] if resume_metadata else None,
        "resumed_partial_trial_id": resume_record.get("trial_id") if resume_record else None,
        "initial_charged_tokens": initial_charged,
        "no_retries": True,
    })
    save_json(args.out / "scores.json", scores)
    save_json(args.out / "ledger.json", {
        "status": scores["status"],
        "attempted_trials": len(records),
        "planned_trials": len(requests),
        "charged_tokens": budget.charged,
        "reserved_tokens": budget.reserved,
        "token_cap": budget.cap,
        "input_sha256": scores["input_sha256"],
        "manifest_sha256": scores["manifest_sha256"],
        "resumed_from": scores["resumed_from"],
        "resumed_partial_trial_id": scores["resumed_partial_trial_id"],
        "initial_charged_tokens": initial_charged,
        "no_retries": True,
    })
    return scores


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run native CostBench tools from frozen paired checkpoints."
    )
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=HERE / "live_results" / "deepseek-flash")
    parser.add_argument("--resume-from", type=Path, default=None, help="Resume an incomplete run from its saved responses, ledger and scores.")
    parser.add_argument("--live", action="store_true", help="Authorize billable DeepSeek API calls.")
    parser.add_argument("--limit", type=int, default=100, help="Number of frozen trials to validate/run.")
    parser.add_argument("--trial-ids", type=str, default="", help="Optional comma-separated trial IDs.")
    parser.add_argument("--cap", type=int, default=DEFAULT_TOKEN_CAP)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-tool-steps", type=int, default=DEFAULT_MAX_TOOL_STEPS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.limit <= 0 or args.cap <= 0 or args.timeout <= 0:
        raise ValueError("limit, cap and timeout must be positive.")
    if args.max_tool_steps <= 0 or args.max_tokens <= 0:
        raise ValueError("max-tool-steps and max-tokens must be positive.")

    # CostBench resolves several runtime assets relative to its checkout root.
    # Resolve caller paths first, then run the native environment from that root.
    args.costbench_root = args.costbench_root.resolve()
    args.data_dir = args.data_dir.resolve()
    args.out = args.out.resolve()
    if args.resume_from is not None:
        args.resume_from = args.resume_from.resolve()
        if not args.live:
            raise ValueError("--resume-from requires --live.")
        if args.limit != 100 or args.trial_ids:
            raise ValueError("--resume-from requires the full 100-trial cohort.")
    os.chdir(args.costbench_root)

    requests, manifest, registry = load_frozen_inputs(args.data_dir)
    if args.trial_ids:
        wanted = {value.strip() for value in args.trial_ids.split(",") if value.strip()}
        requests = [row for row in requests if row["trial_id"] in wanted]
        if len(requests) != len(wanted):
            raise ValueError("One or more requested trial IDs are absent from the frozen dataset.")
    else:
        requests = requests[: args.limit]
    if not requests:
        raise ValueError("No trials selected.")

    query_path = args.costbench_root / "env" / "data" / "runtime" / "queries" / "queries.json"
    query_rows = json.loads(query_path.read_text(encoding="utf-8"))
    queries = {
        row["query_id"].strip("<>"): row
        for row in query_rows
    }
    registry_rows = {
        row["task_id"]: row
        for row in registry["selection"]["task_ids"]
    }
    costbench = load_costbench(args.costbench_root)

    prepared_rows = []
    for request in requests:
        query_id = request["query_id"]
        if query_id not in queries or query_id not in registry_rows:
            raise ValueError(f"Source query or task registry entry missing: {query_id}")
        prepared_rows.append(
            prepare_trial(
                request,
                manifest[request["trial_id"]],
                queries[query_id],
                registry_rows[query_id],
                costbench,
            )
        )

    # Pair audit is applied whenever both conditions for a task are selected.
    prepared_summary = audit_prepared_pairs(prepared_rows) if len(prepared_rows) == 100 else {
        "trials_prepared": len(prepared_rows),
        "base_tasks_prepared": len({row["query_id"] for row in prepared_rows}),
        "conditions_prepared": dict(Counter(row["condition"] for row in prepared_rows)),
    }
    report = {
        "status": "validated_no_model_calls",
        "upstream_revision": costbench["revision"],
        "model": MODEL,
        "mode": "live" if args.live else "dry_run",
        "selected_trials": len(requests),
        "prepared": prepared_summary,
        "checkpoint_hashes_verified": len(prepared_rows),
        "prefixes_replayed": sum(bool(row["prefix"]) for row in prepared_rows),
        "native_tool_interfaces_built": len(prepared_rows),
        "model_calls": 0,
        "budget_charged": 0,
        "trial_ids": [row["trial_id"] for row in prepared_rows],
    }
    if not args.live:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    scores = asyncio.run(run_live(
        prepared_rows, requests, manifest, costbench, args
    ))
    print(json.dumps(scores, ensure_ascii=False, indent=2))
    return 0 if (
        scores["status"] == "complete"
        and scores["api_error_trials"] == 0
        and scores["runner_error_trials"] == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
