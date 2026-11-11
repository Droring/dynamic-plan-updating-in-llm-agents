#!/usr/bin/env python3
"""Replay the archived graph-planner first action in four isolated native restores.

Offline-only: no provider client, no model prompt, no reference solver decision.
Each arm is a fresh OS process that reconstructs the same frozen CostBench
checkpoint and re-executes the exact archived native tool call.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import run_bounded_verifier_confirmation as confirmation
import run_official_harness as native

HERE = Path(__file__).resolve().parent
TASKS = ("Query00178", "Query00351", "Query00549", "Query00689", "Query00851")
ENVIRONMENTS = ("RETAIN", "SWITCH")
ARMS = ("A", "B", "C", "D")
POLICIES = ("incumbent", "candidate_gate", "graph_planner")
TOL = 1e-6


def select_common_actions(rows):
    expected = {(q, e, p) for q in TASKS for e in ENVIRONMENTS for p in POLICIES}
    indexed = {}
    for row in rows:
        key = (row.get("query_id"), row.get("environment"), row.get("policy"))
        if key not in expected or key in indexed:
            raise ValueError(f"Unexpected or duplicate archived trajectory: {key}")
        indexed[key] = row
    if set(indexed) != expected or len(rows) != 30:
        raise ValueError("Archive must contain exactly 5 tasks × 2 environments × 3 policies")
    actions = []
    for query_id in TASKS:
        for environment in ENVIRONMENTS:
            row = indexed[(query_id, environment, "graph_planner")]
            steps = row.get("steps") or []
            if not row.get("reached_goal") or not steps:
                raise ValueError(f"Graph-planner source trajectory incomplete: {query_id}/{environment}")
            first = steps[0]
            tool = first.get("tool")
            arguments = first.get("arguments")
            output = first.get("output")
            if not tool or not isinstance(arguments, str) or not isinstance(output, str):
                raise ValueError("Archived first action is missing its exact arguments or native result")
            json.loads(arguments)
            if not first.get("success") or row.get("path", [None])[0] != tool:
                raise ValueError("Archived graph-planner first action is not a successful path prefix")
            if row.get("controlled_first_action") != tool:
                raise ValueError("Archived controlled action differs from executed first tool")
            actions.append({
                "query_id": query_id,
                "environment": environment,
                "source_trial_id": row["source_trial_id"],
                "checkpoint_sha256": row["checkpoint_sha256"],
                "tool": tool,
                "arguments": arguments,
                "arguments_sha256": native.sha_bytes(arguments.encode("utf-8")),
                "tool_result": output,
                "tool_result_sha256": native.sha_bytes(output.encode("utf-8")),
                "recorded_cost": float(first["cost"]),
                "recorded_success": bool(first["success"]),
            })
    if len(actions) != 10:
        raise ValueError("Expected ten common post-first-action checkpoints")
    return actions


def validate_branch_records(actions, branch_outputs):
    if set(branch_outputs) != set(ARMS):
        raise ValueError("Need four independent A/B/C/D restoration outputs")
    by_arm = {}
    for arm, payload in branch_outputs.items():
        if payload.get("arm") != arm or payload.get("status") != "worker_complete":
            raise ValueError(f"Restoration worker failed for arm {arm}")
        rows = payload.get("rows", [])
        index = {(r["query_id"], r["environment"]): r for r in rows}
        if len(rows) != 10 or len(index) != 10:
            raise ValueError(f"Arm {arm} did not restore all ten checkpoints")
        by_arm[arm] = index
    summaries = []
    for action in actions:
        key = (action["query_id"], action["environment"])
        group = [by_arm[arm][key] for arm in ARMS]
        if len({r["process_id"] for r in group}) != 4:
            raise ValueError(f"Branches do not have four distinct process restorations: {key}")
        required_equal = (
            "checkpoint_sha256", "source_trial_id", "tool", "arguments_sha256",
            "tool_result_sha256", "initial_state_sha256", "post_action_state_sha256",
            "tool_registry_sha256", "output_type",
        )
        for field in required_equal:
            if len({r[field] for r in group}) != 1:
                raise ValueError(f"Four-arm mismatch for {key}: {field}")
        if not all(r["tool_result"] == action["tool_result"] for r in group):
            raise ValueError(f"Native result differs from archived source in at least one branch for {key}")
        if not all(r["arguments"] == action["arguments"] for r in group):
            raise ValueError(f"Exact native arguments differ from archived source in at least one branch for {key}")
        if not all(r["native_success"] for r in group):
            raise ValueError(f"Native first action failed in one or more restored branches: {key}")
        summaries.append({
            "query_id": key[0], "environment": key[1],
            "tool": action["tool"],
            "arguments_sha256": action["arguments_sha256"],
            "tool_result_sha256": action["tool_result_sha256"],
            "checkpoint_sha256": action["checkpoint_sha256"],
            "initial_state_sha256": group[0]["initial_state_sha256"],
            "post_action_state_sha256": group[0]["post_action_state_sha256"],
            "four_independent_processes": True,
            "exact_arguments_match": True,
            "exact_native_result_match": True,
            "post_action_state_match": True,
        })
    return summaries


def worker(costbench_root: Path, actions_path: Path, arm: str, out_path: Path):
    actions = json.loads(actions_path.read_text(encoding="utf-8"))
    trials, cb = confirmation.load_checkpoints(costbench_root.resolve())
    lookup = {(t["query_id"], t["environment_condition"]): t for t in trials}
    if len(lookup) != 20:
        raise ValueError("Pinned checkpoint reconstruction did not return 20 paired checkpoints")
    pid = os.getpid()
    rows = []
    for action in actions:
        key = (action["query_id"], action["environment"])
        trial = lookup.get(key)
        if trial is None:
            raise ValueError(f"Missing restored checkpoint: {key}")
        prepared = trial["prepared"]
        if prepared["checkpoint_sha256"] != action["checkpoint_sha256"]:
            raise ValueError(f"Frozen checkpoint hash mismatch: {key}")
        if trial["source_trial_id"] != action["source_trial_id"]:
            raise ValueError(f"Frozen source request mismatch: {key}")
        tool = prepared["tool_objects"].get(action["tool"])
        if tool is None:
            raise ValueError(f"Archived first action not present in native tool registry: {key}")
        if not set(tool.input_types).issubset(set(prepared["state"])):
            raise ValueError(f"Archived first action is infeasible at restored checkpoint: {key}")
        if abs(float(tool.cost) - action["recorded_cost"]) > TOL:
            raise ValueError(f"Native action value changed since archived execution: {key}")
        interfaces = [x for x in prepared["tool_interfaces"]
                      if x["function"]["name"] == action["tool"]]
        if len(interfaces) != 1:
            raise ValueError(f"Expected one native function schema for {key}")
        initial_state = sorted(prepared["state"])
        initial_state_sha = native.canonical_sha(initial_state)
        registry_sha = native.canonical_sha(prepared["tool_interfaces"])
        result = cb["official_run"]._execute_tool_simulation(
            tool_obj=tool,
            arguments_str=action["arguments"],
            refinement_level=native.REFINEMENT_LEVEL,
            available_tools=prepared["tool_objects"],
        )
        result_text = str(result)
        success = not (isinstance(result, str) and result.startswith(native.ERROR_PREFIXES))
        if not success:
            raise RuntimeError(f"Native tool execution returned an error for {key}: {result_text}")
        if result_text != action["tool_result"]:
            raise ValueError(f"Exact archived native result mismatch for {key}")
        post_state = set(prepared["state"])
        post_state.add(tool.output_type)
        rows.append({
            "query_id": key[0], "environment": key[1],
            "source_trial_id": trial["source_trial_id"],
            "checkpoint_sha256": prepared["checkpoint_sha256"],
            "tool": action["tool"], "arguments": action["arguments"],
            "arguments_sha256": native.sha_bytes(action["arguments"].encode("utf-8")),
            "tool_result": result_text,
            "tool_result_sha256": native.sha_bytes(result_text.encode("utf-8")),
            "native_success": success,
            "recorded_cost": float(tool.cost),
            "output_type": tool.output_type,
            "initial_state_sha256": initial_state_sha,
            "post_action_state_sha256": native.canonical_sha(sorted(post_state)),
            "tool_registry_sha256": registry_sha,
            "process_id": pid,
        })
    payload = {"status":"worker_complete","arm":arm,"process_id":pid,"rows":rows}
    out_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def run_preflight(costbench_root: Path, trajectories: Path, out: Path):
    archived = [json.loads(line) for line in trajectories.read_text(encoding="utf-8").splitlines() if line.strip()]
    actions = select_common_actions(archived)
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="common-action-restore-") as temp:
        temp_path = Path(temp)
        actions_path = temp_path / "common-actions.json"
        actions_path.write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding="utf-8")
        outputs = {}
        for arm in ARMS:
            worker_path = temp_path / f"restore-{arm}.json"
            command = [
                sys.executable, str(Path(__file__).resolve()),
                "--worker", "--costbench-root", str(costbench_root.resolve()),
                "--actions", str(actions_path), "--arm", arm, "--worker-out", str(worker_path),
            ]
            completed = subprocess.run(command,text=True,capture_output=True)
            if completed.returncode != 0 or not worker_path.is_file():
                raise RuntimeError(
                    f"Isolated restoration failed for {arm}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            outputs[arm] = json.loads(worker_path.read_text(encoding="utf-8"))
        rows = validate_branch_records(actions,outputs)
    report = {
        "status":"passed",
        "provider_calls":0,
        "model_calls":0,
        "base_tasks":len(TASKS),
        "environment_checkpoints":len(actions),
        "independent_restoration_processes":len(ARMS),
        "restored_branch_contexts":len(actions)*len(ARMS),
        "native_first_action_replays":len(actions)*len(ARMS),
        "exact_archived_arguments_matches":len(rows)*len(ARMS),
        "exact_archived_native_result_matches":len(rows)*len(ARMS),
        "post_action_state_matches_across_branches":len(rows),
        "all_checkpoints_passed":len(rows)==10,
        "arms_are_restoration_slots_not_prompt_results":True,
        "rows":rows,
    }
    (out/"common_action_restoration_preflight.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},ensure_ascii=False,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--trajectories",type=Path)
    p.add_argument("--out",type=Path)
    p.add_argument("--worker",action="store_true")
    p.add_argument("--actions",type=Path)
    p.add_argument("--arm",choices=ARMS)
    p.add_argument("--worker-out",type=Path)
    args=p.parse_args()
    if args.worker:
        if not all((args.actions,args.arm,args.worker_out)):
            p.error("Worker mode requires --actions, --arm and --worker-out")
        worker(args.costbench_root,args.actions,args.arm,args.worker_out)
        return
    if not args.trajectories or not args.out:
        p.error("Preflight mode requires --trajectories and --out")
    run_preflight(args.costbench_root,args.trajectories,args.out)


if __name__=="__main__":
    main()
