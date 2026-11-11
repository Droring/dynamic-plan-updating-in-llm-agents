#!/usr/bin/env python3
"""Replay one common nonterminal action in four isolated native restores.

The same feasible action and exact argument string are selected for both
RETAIN/SWITCH states of each task. Its environment-specific native result is
then replayed independently in A/B/C/D. Offline only; no provider calls.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import run_bounded_verifier_confirmation as confirmation
import run_official_harness as native

HERE = Path(__file__).resolve().parent
TASKS = ("Query00178","Query00351","Query00549","Query00689","Query00851")
ENVIRONMENTS = ("RETAIN","SWITCH")
ARMS = ("A","B","C","D")
POLICIES = ("graph_planner","candidate_gate","incumbent")
TOL = 1e-6


def select_common_actions(rows, trial_lookup=None):
    expected={(q,e,p) for q in TASKS for e in ENVIRONMENTS for p in ("incumbent","candidate_gate","graph_planner")}
    indexed={}
    for row in rows:
        key=(row.get("query_id"),row.get("environment"),row.get("policy"))
        if key not in expected or key in indexed:
            raise ValueError(f"Unexpected or duplicate archived trajectory: {key}")
        indexed[key]=row
    if set(indexed)!=expected or len(rows)!=30:
        raise ValueError("Archive must contain exactly 5 tasks × 2 environments × 3 policies")
    actions=[]
    selected_sources={}
    for query_id in TASKS:
        candidates=[]
        # Deterministic source order: SWITCH before RETAIN, graph planner before
        # candidate gate before incumbent. Only an actually executed multi-step
        # trajectory can supply a nonterminal common prefix.
        for environment in ("SWITCH","RETAIN"):
            for policy in POLICIES:
                row=indexed[(query_id,environment,policy)]
                steps=row.get("steps") or []
                if not row.get("reached_goal") or len(steps)<2:
                    continue
                first=steps[0]
                if not first.get("success") or not first.get("tool") or not isinstance(first.get("arguments"),str):
                    continue
                json.loads(first["arguments"])
                candidates.append((row,first))
        selected=None
        for row,first in candidates:
            if trial_lookup is not None:
                feasible=True
                for environment in ENVIRONMENTS:
                    trial=trial_lookup.get((query_id,environment))
                    if trial is None:
                        feasible=False
                        break
                    prepared=trial["prepared"]
                    tool=prepared["tool_objects"].get(first["tool"])
                    if (tool is None or not set(tool.input_types).issubset(set(prepared["state"]))
                            or tool.output_type==prepared["goal_type"]):
                        feasible=False
                        break
                if not feasible:
                    continue
            selected=(row,first)
            break
        if selected is None:
            raise ValueError(f"No common feasible nonterminal action exists for paired task {query_id}")
        source_row,source_step=selected
        source_env=source_row["environment"]
        source_policy=source_row["policy"]
        selected_sources[query_id]={
            "source_environment":source_env,"source_policy":source_policy,
            "source_trial_id":source_row["source_trial_id"],
            "tool":source_step["tool"],
            "arguments":source_step["arguments"],
        }
        for environment in ENVIRONMENTS:
            paired_row=indexed[(query_id,environment,"graph_planner")]
            if paired_row["checkpoint_sha256"]!=source_row["checkpoint_sha256"]:
                raise ValueError(f"RETAIN/SWITCH checkpoint hash mismatch for {query_id}")
            actions.append({
                "query_id":query_id,"environment":environment,
                "source_environment":source_env,"source_policy":source_policy,
                "source_action_trial_id":source_row["source_trial_id"],
                "paired_source_trial_id":paired_row["source_trial_id"],
                "checkpoint_sha256":paired_row["checkpoint_sha256"],
                "tool":source_step["tool"],
                "arguments":source_step["arguments"],
                "arguments_sha256":native.sha_bytes(source_step["arguments"].encode("utf-8")),
                "expected_archived_tool_result":source_step["output"] if environment==source_env else None,
                "expected_archived_tool_result_sha256":(
                    native.sha_bytes(source_step["output"].encode("utf-8")) if environment==source_env else None
                ),
                "recorded_cost":float(source_step["cost"]) if environment==source_env else None,
            })
    if len(actions)!=10:
        raise ValueError("Expected ten paired task/environment common-action replays")
    return actions


def validate_branch_records(actions,branch_outputs):
    if set(branch_outputs)!=set(ARMS):
        raise ValueError("Need four independent A/B/C/D restoration outputs")
    by_arm={}
    for arm,payload in branch_outputs.items():
        if payload.get("arm")!=arm or payload.get("status")!="worker_complete":
            raise ValueError(f"Restoration worker failed for arm {arm}")
        rows=payload.get("rows",[])
        index={(r["query_id"],r["environment"]):r for r in rows}
        if len(rows)!=10 or len(index)!=10:
            raise ValueError(f"Arm {arm} did not restore all ten checkpoints")
        by_arm[arm]=index
    summaries=[]
    for action in actions:
        key=(action["query_id"],action["environment"])
        group=[by_arm[arm][key] for arm in ARMS]
        if len({r["process_id"] for r in group})!=4:
            raise ValueError(f"Branches do not have four distinct process restorations: {key}")
        required_equal=(
            "checkpoint_sha256","paired_source_trial_id","tool","arguments_sha256",
            "tool_result_sha256","initial_state_sha256","post_action_state_sha256",
            "tool_registry_sha256","output_type",
        )
        for field in required_equal:
            if len({r[field] for r in group})!=1:
                raise ValueError(f"Four-arm mismatch for {key}: {field}")
        if not all(r["arguments"]==action["arguments"] for r in group):
            raise ValueError(f"Exact common arguments differ across arms: {key}")
        if not all(r["native_success"] for r in group):
            raise ValueError(f"Native common action failed in at least one arm: {key}")
        if action["environment"]==action["source_environment"]:
            if not all(r["tool_result"]==action["expected_archived_tool_result"] for r in group):
                raise ValueError(f"Source-environment native result differs from archived source: {key}")
        summaries.append({
            "query_id":key[0],"environment":key[1],
            "source_environment":action["source_environment"],
            "source_policy":action["source_policy"],
            "source_action_trial_id":action["source_action_trial_id"],
            "paired_source_trial_id":action["paired_source_trial_id"],
            "tool":action["tool"],
            "arguments_sha256":action["arguments_sha256"],
            "tool_result":group[0]["tool_result"],
            "tool_result_sha256":group[0]["tool_result_sha256"],
            "checkpoint_sha256":action["checkpoint_sha256"],
            "initial_state_sha256":group[0]["initial_state_sha256"],
            "post_action_state_sha256":group[0]["post_action_state_sha256"],
            "tool_registry_sha256":group[0]["tool_registry_sha256"],
            "output_type":group[0]["output_type"],
            "four_independent_processes":True,
            "exact_arguments_match_across_arms":True,
            "native_result_match_across_arms":True,
            "archived_result_match":True if action["environment"]==action["source_environment"] else None,
            "post_action_state_match":True,
        })
    # A task's paired environments must receive the same tool and exact arguments.
    for query_id in TASKS:
        pair=[a for a in actions if a["query_id"]==query_id]
        if len(pair)!=2 or pair[0]["tool"]!=pair[1]["tool"] or pair[0]["arguments"]!=pair[1]["arguments"]:
            raise ValueError(f"RETAIN/SWITCH do not share the same common action: {query_id}")
        if pair[0]["source_environment"]!=pair[1]["source_environment"] or pair[0]["source_policy"]!=pair[1]["source_policy"]:
            raise ValueError(f"Paired common-action source differs: {query_id}")
    return summaries


def worker(costbench_root:Path,actions_path:Path,arm:str,out_path:Path):
    actions=json.loads(actions_path.read_text(encoding="utf-8"))
    trials,cb=confirmation.load_checkpoints(costbench_root.resolve())
    lookup={(t["query_id"],t["environment_condition"]):t for t in trials}
    if len(lookup)!=20:
        raise ValueError("Pinned checkpoint reconstruction did not return 20 paired checkpoints")
    pid=os.getpid()
    rows=[]
    for action in actions:
        key=(action["query_id"],action["environment"])
        trial=lookup.get(key)
        if trial is None:
            raise ValueError(f"Missing restored checkpoint: {key}")
        prepared=trial["prepared"]
        if prepared["checkpoint_sha256"]!=action["checkpoint_sha256"]:
            raise ValueError(f"Frozen checkpoint hash mismatch: {key}")
        if trial["source_trial_id"]!=action["paired_source_trial_id"]:
            raise ValueError(f"Paired source request mismatch: {key}")
        tool=prepared["tool_objects"].get(action["tool"])
        if tool is None or not set(tool.input_types).issubset(set(prepared["state"])):
            raise ValueError(f"Common action is not feasible at restored checkpoint: {key}")
        if tool.output_type==prepared["goal_type"]:
            raise ValueError(f"Common action terminates the task before continuation: {key}")
        if action["environment"]==action["source_environment"] and abs(float(tool.cost)-float(action["recorded_cost"]))>TOL:
            raise ValueError(f"Source-environment action value changed: {key}")
        interfaces=[x for x in prepared["tool_interfaces"] if x["function"]["name"]==action["tool"]]
        if len(interfaces)!=1:
            raise ValueError(f"Native function schema missing or ambiguous: {key}")
        initial_state=sorted(prepared["state"])
        result=cb["official_run"]._execute_tool_simulation(
            tool_obj=tool,arguments_str=action["arguments"],
            refinement_level=native.REFINEMENT_LEVEL,
            available_tools=prepared["tool_objects"],
        )
        result_text=str(result)
        success=not (isinstance(result,str) and result.startswith(native.ERROR_PREFIXES))
        if not success:
            raise RuntimeError(f"Native common action failed for {key}: {result_text}")
        if action["environment"]==action["source_environment"] and result_text!=action["expected_archived_tool_result"]:
            raise ValueError(f"Source-environment exact result differs from archive: {key}")
        post_state=set(prepared["state"])
        post_state.add(tool.output_type)
        rows.append({
            "query_id":key[0],"environment":key[1],
            "paired_source_trial_id":trial["source_trial_id"],
            "source_action_trial_id":action["source_action_trial_id"],
            "source_environment":action["source_environment"],
            "source_policy":action["source_policy"],
            "checkpoint_sha256":prepared["checkpoint_sha256"],
            "tool":action["tool"],"arguments":action["arguments"],
            "arguments_sha256":native.sha_bytes(action["arguments"].encode("utf-8")),
            "tool_result":result_text,
            "tool_result_sha256":native.sha_bytes(result_text.encode("utf-8")),
            "native_success":success,"recorded_cost":float(tool.cost),
            "output_type":tool.output_type,
            "initial_state_sha256":native.canonical_sha(initial_state),
            "post_action_state_sha256":native.canonical_sha(sorted(post_state)),
            "tool_registry_sha256":native.canonical_sha(prepared["tool_interfaces"]),
            "process_id":pid,
        })
    payload={"status":"worker_complete","arm":arm,"process_id":pid,"rows":rows}
    out_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def run_preflight(costbench_root:Path,trajectories:Path,out:Path):
    archived=[json.loads(x) for x in trajectories.read_text(encoding="utf-8").splitlines() if x.strip()]
    selection_trials,_=confirmation.load_checkpoints(costbench_root.resolve())
    selection_lookup={(t["query_id"],t["environment_condition"]):t for t in selection_trials}
    actions=select_common_actions(archived,selection_lookup)
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="common-action-restore-") as temp:
        temp_path=Path(temp)
        actions_path=temp_path/"common-actions.json"
        actions_path.write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding="utf-8")
        outputs={}
        for arm in ARMS:
            worker_path=temp_path/f"restore-{arm}.json"
            command=[sys.executable,str(Path(__file__).resolve()),"--worker",
                "--costbench-root",str(costbench_root.resolve()),
                "--actions",str(actions_path),"--arm",arm,"--worker-out",str(worker_path)]
            completed=subprocess.run(command,text=True,capture_output=True)
            if completed.returncode!=0 or not worker_path.is_file():
                raise RuntimeError(f"Isolated restoration failed for {arm}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
            outputs[arm]=json.loads(worker_path.read_text(encoding="utf-8"))
        rows=validate_branch_records(actions,outputs)
    report={
        "status":"passed","provider_calls":0,"model_calls":0,
        "base_tasks":len(TASKS),"paired_environment_checkpoints":len(actions),
        "common_nonterminal_actions":len(TASKS),
        "independent_restoration_processes":len(ARMS),
        "restored_branch_contexts":len(actions)*len(ARMS),
        "native_common_action_replays":len(actions)*len(ARMS),
        "exact_common_arguments_matches":len(actions)*len(ARMS),
        "exact_archived_native_result_matches":sum(a["environment"]==a["source_environment"] for a in actions)*len(ARMS),
        "native_result_matches_across_arms":len(actions)*len(ARMS),
        "post_action_state_matches_across_branches":len(actions),
        "paired_environments_share_common_tool_and_arguments":len(TASKS),
        "all_checkpoints_passed":len(rows)==10,
        "action_selection":"first feasible nonterminal action from a previously successful multi-step archived trajectory, fixed across each task's RETAIN/SWITCH pair",
        "rows":rows,
    }
    (out/"common_action_restoration_preflight.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
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
    run_preflight(args.costbench_root.resolve(),args.trajectories.resolve(),args.out.resolve())


if __name__=="__main__":
    main()
