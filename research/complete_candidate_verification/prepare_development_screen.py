"""Provider-free preflight for the frozen 32-trajectory development screen."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .candidate_generator import CandidateGenerator
from .policy_input import (
    canonical_json,
    parse_public_tool_interfaces,
    reject_evaluation_fields,
)
from .run_complete_candidate import (
    load_native_trial,
    make_observation_history,
    make_policy_input_from_prepared,
)

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "DEVELOPMENT_SCREEN_MANIFEST.json"
REPO_ROOT = HERE.parents[1]
SOURCE_FILES = {
    "task_registry_blob_sha": REPO_ROOT / "experiments/paired_50/generated/task_registry_50.json",
    "model_requests_blob_sha": REPO_ROOT / "experiments/paired_50/generated/model_requests_100.jsonl",
    "trial_manifest_blob_sha": REPO_ROOT / "experiments/paired_50/generated/trial_manifest_100.json",
}
_COST_TEXT = re.compile(r"(?i)\\bCost:\\s*[0-9]+(?:\\.[0-9]+)?")


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\\0" + raw).hexdigest()


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _contracts(prepared: dict[str, Any]):
    return parse_public_tool_interfaces(prepared["tool_interfaces"])


def _validate_pair(task: dict[str, Any], retain: dict[str, Any], switch: dict[str, Any]) -> dict[str, Any]:
    fixed_fields = (
        "query_id", "task", "goal_type", "checkpoint_sha256", "state", "prefix",
        "prefix_name", "prefix_observation", "prefix_output_id",
        "incumbent_suffix", "changed_tool", "user_request",
    )
    for field in fixed_fields:
        if retain.get(field) != switch.get(field):
            raise ValueError(f"{task['query_id']} paired {field} mismatch")
    if retain["checkpoint_sha256"] != task["checkpoint_sha256"]:
        raise ValueError(f"{task['query_id']} checkpoint hash differs from frozen manifest")

    rc, sc = _contracts(retain), _contracts(switch)
    if set(rc) != set(sc):
        raise ValueError(f"{task['query_id']} tool catalogue names differ across conditions")
    changed_costs = []
    for name in sorted(rc):
        left, right = rc[name], sc[name]
        if left.required_inputs != right.required_inputs or left.output_type != right.output_type:
            raise ValueError(f"{task['query_id']} tool schema changed across conditions: {name}")
        if canonical_json(left.interface["function"]["parameters"]) != canonical_json(
            right.interface["function"]["parameters"]
        ):
            raise ValueError(f"{task['query_id']} tool parameter schema changed: {name}")
        left_description = left.interface["function"]["description"]
        right_description = right.interface["function"]["description"]
        if _COST_TEXT.sub("Cost: <value>", left_description) != _COST_TEXT.sub(
            "Cost: <value>", right_description
        ):
            raise ValueError(f"{task['query_id']} tool description changed beyond its cost: {name}")
        if abs(left.cost - right.cost) > 1e-9:
            changed_costs.append(name)
    if changed_costs != [retain["changed_tool"]]:
        raise ValueError(
            f"{task['query_id']} expected one changed tool {retain['changed_tool']}, got {changed_costs}"
        )
    if abs(float(retain["native_regret_audit"])) > 1e-6:
        raise ValueError(f"{task['query_id']} RETAIN fixture is not optimal")
    if float(switch["native_regret_audit"]) < 1.0 - 1e-6:
        raise ValueError(f"{task['query_id']} SWITCH fixture is not sufficiently suboptimal")
    return {
        "query_id": task["query_id"],
        "checkpoint_sha256": retain["checkpoint_sha256"],
        "changed_tool": retain["changed_tool"],
        "incumbent_suffix": retain["incumbent_suffix"],
        "state_types": sorted(retain["state"]),
        "prefix_tool": retain["prefix_name"],
        "prefix_output_id": retain["prefix_output_id"],
        "changed_cost_tools": changed_costs,
        "retain_incumbent_gap": round(float(retain["native_regret_audit"]), 6),
        "switch_incumbent_gap": round(float(switch["native_regret_audit"]), 6),
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_hashes = {}
    for field, path in SOURCE_FILES.items():
        if not path.is_file():
            raise FileNotFoundError(f"frozen source file is missing: {path}")
        actual = git_blob_sha(path)
        if actual != manifest["source"][field]:
            raise ValueError(f"frozen source blob mismatch for {path.name}: {actual}")
        source_hashes[field] = actual
    root = args.costbench_root.resolve()
    loaded: dict[str, dict[str, tuple[Any, ...]]] = {}
    prompts: dict[str, Any] = {}
    pair_audits = []
    prompt_hashes = []
    tasks = manifest["selection"]["tasks"]
    if len({row["query_id"] for row in tasks}) != len(tasks):
        raise ValueError("duplicate base task IDs in development manifest")
    trial_ids = [row["trial_ids"][condition] for row in tasks for condition in ("RETAIN", "SWITCH")]
    if len(set(trial_ids)) != len(trial_ids):
        raise ValueError("duplicate trial IDs in development manifest")

    for task in tasks:
        loaded[task["query_id"]] = {}
        for condition in ("RETAIN", "SWITCH"):
            native, costbench, prepared, query = load_native_trial(
                root, task["query_id"], condition, minimum_plan_length=1
            )
            expected_trial = task["trial_ids"][condition]
            if prepared["trial_id"] != expected_trial:
                raise ValueError(
                    f"{task['query_id']} {condition} trial ID mismatch: "
                    f"{prepared['trial_id']} != {expected_trial}"
                )
            if prepared["condition"] != condition:
                raise ValueError(f"{task['query_id']} loaded the wrong condition")
            history = make_observation_history(prepared, query, native)
            policy = make_policy_input_from_prepared(prepared, history)
            payload = policy.prompt_payload(include_incumbent=True)
            reject_evaluation_fields(payload)
            generator = CandidateGenerator(lambda **_: None)
            repair_messages = generator._messages(policy, "repair")
            fresh_messages = generator._messages(policy, "fresh")
            baseline_messages = generator._messages(policy, "fresh")
            for prompt in (repair_messages, fresh_messages, baseline_messages):
                reject_evaluation_fields(prompt)
            if canonical_json(fresh_messages) != canonical_json(baseline_messages):
                raise ValueError("fresh candidate prompts are not reproducible")
            cell_key = f"{task['query_id']}::{condition}"
            prompts[cell_key] = {
                "repair": repair_messages,
                "fresh": fresh_messages,
                "baseline_fresh_1": fresh_messages,
                "baseline_fresh_2": baseline_messages,
                "prompt_sha256": {
                    "repair": sha256(repair_messages),
                    "fresh": sha256(fresh_messages),
                },
                "policy_input_sha256": sha256(payload),
                "tool_catalog_sha256": policy.tool_catalog_sha256,
                "state_sha256": policy.state_sha256,
                "observation_history_sha256": sha256(list(history)),
            }
            prompt_hashes.append({
                "task_id": task["query_id"],
                "condition": condition,
                "repair": sha256(repair_messages),
                "fresh": sha256(fresh_messages),
                "tool_catalog": policy.tool_catalog_sha256,
                "state": policy.state_sha256,
                "history": sha256(list(history)),
            })
            loaded[task["query_id"]][condition] = (native, costbench, prepared, query)
    for task in tasks:
        retain = loaded[task["query_id"]]["RETAIN"][2]
        switch = loaded[task["query_id"]]["SWITCH"][2]
        pair_audits.append(_validate_pair(task, retain, switch))

    expected_cells = len(tasks) * 2 * 2
    if expected_cells != manifest["design"]["task_condition_method_cells"]:
        raise ValueError("frozen design cell count does not equal 32")
    return {
        "schema": "complete-candidate-development-screen-preflight-v1",
        "status": "passed",
        "provider_calls": 0,
        "source_blob_hashes_verified": source_hashes,
        "upstream_costbench_revision": manifest["design"]["upstream_costbench_revision"],
        "model_configuration": {
            "model": manifest["design"]["model"],
            "temperature": manifest["design"]["temperature"],
            "thinking": manifest["design"]["thinking"],
            "max_output_tokens": manifest["design"]["maximum_output_tokens_per_call"],
        },
        "base_tasks": len(tasks),
        "paired_checkpoints": len(tasks) * 2,
        "planned_trajectories": manifest["design"]["full_native_trajectories"],
        "candidate_methods": [row["id"] for row in manifest["design"]["methods"]],
        "pair_audits": pair_audits,
        "prompt_hashes": prompt_hashes,
        "checks": {
            "trial_ids_match_frozen_manifest": True,
            "retain_switch_checkpoint_state_and_prefix_match": True,
            "tool_schemas_match_except_one_changed_tool_cost": True,
            "retain_and_switch_native_value_labels_verified_offline": True,
            "evaluation_fields_absent_from_policy_prompts": True,
            "proposed_and_baseline_share_fresh_prompt_template": True,
            "provider_calls": 0,
        },
        "prompts": prompts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free 32-trajectory development-screen preflight")
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("outputs/development_screen_preflight"))
    args = parser.parse_args()
    args.costbench_root = args.costbench_root.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    result = prepare(args)
    (args.out / "preflight.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "prompts"},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "prompts.json").write_text(
        json.dumps(result["prompts"], ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "provider_calls": result["provider_calls"],
        "base_tasks": result["base_tasks"],
        "paired_checkpoints": result["paired_checkpoints"],
        "planned_trajectories": result["planned_trajectories"],
        "prompt_hashes": len(result["prompt_hashes"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
