#!/usr/bin/env python3
"""Build and audit the frozen Plan Handoff × Observed-State 2×2 prompts.

Offline only. The graph planner supplies a diagnostic replacement suffix in B/D;
no optimal value, regret, answer key or reference label is included in model input.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import graph_planning_baseline as graph
import run_bounded_verifier_confirmation as confirmation
import run_official_harness as native
from preflight_common_action_restoration import (
    ARMS, ENVIRONMENTS, TASKS, select_common_actions,
)

MAX_TOKENS = 2048
REPETITIONS = 2


def build_initial_ledger(prepared, action, tool):
    """Only facts explicitly present in the checkpoint or common native result."""
    initial_types = sorted(prepared["state"])
    prefix_name = prepared.get("prefix_name")
    prefix_observation = prepared.get("prefix_observation") or ""
    source = "CHECKPOINT-STATE"
    if prefix_name:
        source = f"PREFIX-ACTION:{prefix_name}"
    return {
        "confirmed": [
            {
                "fact": "Available type set at the frozen checkpoint: " + ", ".join(initial_types),
                "source_action": source,
                "observation_id": "OBS-CHECKPOINT",
                "exact_observation": prefix_observation,
            },
            {
                "fact": f"Common action {action['tool']} completed successfully; declared output type {tool.output_type} is now available.",
                "source_action": "ACT-001:" + action["tool"],
                "observation_id": "OBS-001",
                "exact_observation": action["tool_result"],
            },
        ],
        "invalidated": [],
        "unknown": [
            "Semantic attributes not explicitly stated in the visible checkpoint, tool schema or native observations remain unknown; no hidden simulator state is inferred."
        ],
    }


def update_ledger(ledger, action_id, tool_name, output_type, observation, success):
    """Deterministic monotonic typed-state renderer; never infers semantic invalidation."""
    updated = copy.deepcopy(ledger)
    if success:
        fact = f"Tool {tool_name} completed successfully; declared output type {output_type} is available."
        updated["confirmed"].append({
            "fact": fact,
            "source_action": f"{action_id}:{tool_name}",
            "observation_id": f"OBS-{action_id}",
            "exact_observation": str(observation),
        })
    else:
        updated["unknown"].append(
            f"Result of {tool_name} ({action_id}) is unsuccessful; its state effect is unknown."
        )
    # CostBench's typed state is monotonic: no prior type is invalidated merely
    # because another output was added. Semantic invalidation is not inferred.
    return updated


def render_ledger(ledger):
    lines = ["Confirmed:"]
    lines.extend(
        f"- {item['fact']} Source: {item['source_action']}; {item['observation_id']}: {item['exact_observation']}"
        for item in ledger["confirmed"]
    )
    lines.append("Invalidated:")
    if ledger["invalidated"]:
        lines.extend(f"- {x}" for x in ledger["invalidated"])
    else:
        lines.append("- None observed in the available native evidence.")
    lines.append("Unknown:")
    lines.extend(f"- {x}" for x in ledger["unknown"])
    return "\n".join(lines)


def build_arm_message(arm, replacement_path, ledger):
    plan_factor = arm in ("B", "D")
    state_factor = arm in ("C", "D")
    if plan_factor:
        plan_text = (
            "An external graph planner computed the following complete continuation "
            "from the actual post-action typed state. This is the current plan. "
            "The previously supplied plan is superseded. Do not repeat the already "
            "executed common first action.\n"
            "Current replacement plan: " + " -> ".join(replacement_path)
        )
    else:
        plan_text = (
            "No replacement plan is supplied. The previously supplied plan remains "
            "in the conversation history as the original plan context. The common "
            "first action shown in the tool history has already completed; do not repeat it."
        )
    if state_factor:
        ledger_text = render_ledger(ledger)
    else:
        ledger_text = (
            "No separate state ledger is supplied. Use the original checkpoint, "
            "native tool-call history and exact tool observations."
        )
    return (
        "[Post-action continuation checkpoint]\n"
        "The common first action above has already been executed successfully. "
        "Continue from its actual returned observation. Make one next native tool "
        "call at a time until the goal is reached.\n\n"
        "[Plan handoff]\n" + plan_text + "\n\n"
        "[Observed-state ledger]\n" + ledger_text
    )


def build_requests(trajectories, restoration, costbench_root, repetitions=REPETITIONS):
    if restoration.get("status") != "passed" or restoration.get("provider_calls") != 0:
        raise ValueError("A passed provider-free common-action restoration report is required")
    if restoration.get("restored_branch_contexts") != 40:
        raise ValueError("Restoration report does not certify all 40 independent contexts")
    actions = select_common_actions(trajectories)
    restore_rows = {(r["query_id"],r["environment"]):r for r in restoration.get("rows",[])}
    if len(restore_rows) != 10:
        raise ValueError("Restoration report must contain ten matched task/environment rows")
    trials, cb = confirmation.load_checkpoints(costbench_root.resolve())
    lookup = {(t["query_id"],t["environment_condition"]):t for t in trials}
    if len(lookup) != 20:
        raise ValueError("Expected 20 reconstructed paired checkpoints")
    requests = []
    cell_summaries = []
    for action in actions:
        key = (action["query_id"],action["environment"])
        trial = lookup.get(key)
        restored = restore_rows.get(key)
        if trial is None or restored is None:
            raise ValueError(f"Missing frozen checkpoint or restoration evidence: {key}")
        prepared = trial["prepared"]
        if prepared["checkpoint_sha256"] != action["checkpoint_sha256"]:
            raise ValueError(f"Checkpoint hash mismatch: {key}")
        if trial["source_trial_id"] != action["source_trial_id"]:
            raise ValueError(f"Source trial mismatch: {key}")
        tool = prepared["tool_objects"].get(action["tool"])
        if tool is None or not set(tool.input_types).issubset(set(prepared["state"])):
            raise ValueError(f"Common first action is not feasible at checkpoint: {key}")
        if abs(float(tool.cost)-action["recorded_cost"])>1e-6:
            raise ValueError(f"Native action value mismatch: {key}")
        schema_rows = [x for x in prepared["tool_interfaces"] if x["function"]["name"]==action["tool"]]
        if len(schema_rows)!=1:
            raise ValueError(f"Native action schema missing or ambiguous: {key}")
        post_state=set(prepared["state"])
        post_state.add(tool.output_type)
        post_state_sha=native.canonical_sha(sorted(post_state))
        registry_sha=native.canonical_sha(prepared["tool_interfaces"])
        if post_state_sha!=restored["post_action_state_sha256"]:
            raise ValueError(f"Post-action state differs from isolated restoration: {key}")
        if registry_sha!=restored["tool_registry_sha256"]:
            raise ValueError(f"Tool schema registry differs from isolated restoration: {key}")
        if action["arguments_sha256"]!=restored["arguments_sha256"] or action["tool_result_sha256"]!=restored["tool_result_sha256"]:
            raise ValueError(f"Action evidence hashes differ from restoration: {key}")
        replanning_input={**prepared,"state":post_state}
        new_path=graph.shortest_feasible_path(replanning_input)
        if new_path is None or not new_path[1]:
            raise ValueError(f"No nonempty continuation remains after common action: {key}")
        replacement_path=list(new_path[1])
        incumbent=list(prepared["incumbent_suffix"])
        remaining_incumbent=incumbent[1:] if incumbent and incumbent[0]==action["tool"] else incumbent
        ledger=build_initial_ledger(prepared,action,tool)
        base_messages=[
            {"role":"system","content":native.make_official_system_prompt(cb["official_run"],prepared["task"])},
            {"role":"user","content":native.make_checkpoint_user_message(prepared)
                +"\n\n[Native action-control evaluation]\n"
                +"For this controlled comparison, your FIRST tool call must invoke "
                +action["tool"]+". Use its actual required arguments based on the current "
                +"observation. After its result, choose subsequent actions freely using "
                +"the available current tools. This first-step restriction is identical "
                +"across all evaluated policies."},
            # The archived full-trajectory artifact does not retain the first
            # assistant turn's free-form content. A normalized null content is
            # therefore used identically in every arm; exact args and result are kept.
            {"role":"assistant","content":None,"tool_calls":[{
                "id":"call_common_first_action","type":"function",
                "function":{"name":action["tool"],"arguments":action["arguments"]}}]},
            {"role":"tool","tool_call_id":"call_common_first_action",
             "name":action["tool"],"content":action["tool_result"]},
        ]
        base_sha=native.canonical_sha(base_messages)
        schema_sha=native.canonical_sha(prepared["tool_interfaces"])
        arm_hashes={}
        for arm in ARMS:
            messages=copy.deepcopy(base_messages)
            messages.append({"role":"user","content":build_arm_message(arm,replacement_path,ledger)})
            payload={
                "model":native.MODEL,"messages":messages,
                "tools":prepared["tool_interfaces"],"temperature":0,
                "max_tokens":MAX_TOKENS,"tool_choice":"required",
                "parallel_tool_calls":False,
                "extra_body":{"thinking":{"type":"disabled"}},
            }
            prompt_sha=native.canonical_sha(payload)
            reservation=native.reservation_for_call(messages,prepared["tool_interfaces"],MAX_TOKENS)
            arm_hashes[arm]={
                "base_history_sha256":base_sha,"tool_schema_sha256":schema_sha,
                "prompt_sha256":prompt_sha,
                "plan_handoff":arm in ("B","D"),
                "state_ledger":arm in ("C","D"),
            }
            for repetition in range(1,repetitions+1):
                requests.append({
                    "trial_id":f"{action['query_id']}_{action['environment']}_{arm}_r{repetition}",
                    "query_id":action["query_id"],"environment":action["environment"],
                    "arm":arm,"repetition":repetition,
                    "checkpoint_sha256":action["checkpoint_sha256"],
                    "source_trial_id":action["source_trial_id"],
                    "common_first_action":action["tool"],
                    "common_arguments":action["arguments"],
                    "common_tool_result":action["tool_result"],
                    "common_tool_result_sha256":action["tool_result_sha256"],
                    "post_action_state_sha256":post_state_sha,
                    "tool_schema_sha256":schema_sha,
                    "updated_plan":replacement_path if arm in ("B","D") else None,
                    "incumbent_plan":incumbent,
                    "remaining_incumbent_after_common_action":remaining_incumbent,
                    "plan_changed_vs_remaining_incumbent":replacement_path!=remaining_incumbent,
                    "initial_ledger":ledger if arm in ("C","D") else None,
                    "reservation_units":reservation,
                    "payload_sha256":prompt_sha,
                    "payload":payload,
                })
        if len({v["base_history_sha256"] for v in arm_hashes.values()})!=1:
            raise ValueError(f"Common executed history differs across arms: {key}")
        if len({v["tool_schema_sha256"] for v in arm_hashes.values()})!=1:
            raise ValueError(f"Tool schemas differ across arms: {key}")
        if len({v["prompt_sha256"] for v in arm_hashes.values()})!=4:
            raise ValueError(f"Factorial prompt conditions are not distinct: {key}")
        if len({v["plan_handoff"] for v in arm_hashes.values()})!=2 or len({v["state_ledger"] for v in arm_hashes.values()})!=2:
            raise ValueError(f"Factorial treatment flags are not balanced: {key}")
        cell_summaries.append({
            "query_id":key[0],"environment":key[1],
            "common_first_action":action["tool"],
            "common_arguments_sha256":action["arguments_sha256"],
            "common_result_sha256":action["tool_result_sha256"],
            "post_action_state_sha256":post_state_sha,
            "updated_plan":replacement_path,
            "remaining_incumbent_plan":remaining_incumbent,
            "plan_changed_vs_remaining_incumbent":replacement_path!=remaining_incumbent,
            "arms":arm_hashes,
        })
    expected=10*len(ARMS)*repetitions
    if len(requests)!=expected:
        raise ValueError(f"Expected {expected} requests, got {len(requests)}")
    return requests,cell_summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--trajectories",type=Path,required=True)
    p.add_argument("--restoration-report",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--repetitions",type=int,default=REPETITIONS)
    args=p.parse_args()
    if args.repetitions<1 or args.repetitions>3:
        p.error("--repetitions must be between 1 and 3 for this development screen")
    trajectories=[json.loads(x) for x in args.trajectories.read_text(encoding="utf-8").splitlines() if x.strip()]
    restoration=json.loads(args.restoration_report.read_text(encoding="utf-8"))
    requests,cells=build_requests(trajectories,restoration,args.costbench_root.resolve(),args.repetitions)
    args.out.mkdir(parents=True,exist_ok=False)
    with (args.out/"requests.jsonl").open("w",encoding="utf-8") as f:
        for row in requests:
            f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    summary={
        "status":"offline_prompt_preflight_passed",
        "provider_calls":0,"model_calls":0,
        "base_tasks":len(TASKS),"environment_checkpoints":len(cells),
        "arms":list(ARMS),"repetitions":args.repetitions,
        "request_count":len(requests),
        "model":native.MODEL,"temperature":0,"thinking":"disabled",
        "max_tokens_per_call":MAX_TOKENS,
        "total_reservation_units":sum(r["reservation_units"] for r in requests),
        "mean_reservation_units_per_request":round(sum(r["reservation_units"] for r in requests)/len(requests),2),
        "all_cells_have_four_arms":all(set(c["arms"])==set(ARMS) for c in cells),
        "common_history_and_tool_schema_matched":True,
        "assistant_freeform_content":"not present in archived full-trajectory records; normalized to null in every arm",
        "plan_changed_cells":sum(c["plan_changed_vs_remaining_incumbent"] for c in cells),
        "plan_unchanged_cells":sum(not c["plan_changed_vs_remaining_incumbent"] for c in cells),
        "cells":cells,
    }
    (args.out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="cells"},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
