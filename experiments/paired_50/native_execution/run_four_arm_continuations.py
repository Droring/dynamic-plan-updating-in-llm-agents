#!/usr/bin/env python3
"""Continue pre-registered first actions from archived four-arm formal responses.

Offline by default. Live mode requires --live and the explicit workflow approval.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_official_harness as native
from run_four_arm_experiment import (
    load_selected_trials, build_trials, make_payload, optimal_first_actions,
    append_jsonl, save_json,
)

TASKS = ("Query00188", "Query00347")
ARMS = ("A", "B", "C", "D")

def prepare(archive, costbench, data_dir):
    manifest = json.loads((HERE / "FOUR_ARM_TASK_MANIFEST.json").read_text())
    selected, _, _ = load_selected_trials(data_dir, costbench, manifest)
    trials = build_trials(selected, manifest, 1, 8, 20261110, task_ids=TASKS)
    with (archive / "responses.jsonl").open(encoding="utf-8") as f:
        records = {r["trial_id"]: r for r in map(json.loads, f)}
    with (archive / "requests.jsonl").open(encoding="utf-8") as f:
        requests = {r["trial_id"]: r for r in map(json.loads, f)}
    chosen = []
    for trial in trials:
        key = trial["trial_id"]
        row = records.get(key)
        req = requests.get(key)
        if row is None or req is None:
            raise ValueError(f"Missing archived first action: {key}")
        if row["first_action_status"] != "executed" or row["tool_call_count"] != 1:
            raise ValueError(f"Invalid archived first action: {key}")
        if row["checkpoint_sha256"] != trial["prepared"]["checkpoint_sha256"]:
            raise ValueError(f"Checkpoint mismatch: {key}")
        if row["request_sha256"] != req["payload_sha256"]:
            raise ValueError(f"Archived request hash mismatch: {key}")
        payload = make_payload(trial, costbench["official_run"])
        if native.canonical_sha(payload) != req["payload_sha256"]:
            raise ValueError(f"Prompt or tool payload changed since formal run: {key}")
        if row["first_action"] != row["raw_tool_calls"][0]["name"]:
            raise ValueError(f"First action mismatch: {key}")
        chosen.append((trial, row, req))
    if len(chosen) != 16:
        raise ValueError(f"Expected 16 continuations, found {len(chosen)}")
    return chosen

async def continue_one(trial, first, official_run, client, budget, max_tokens, max_steps):
    prepared = trial["prepared"]
    payload = make_payload(trial, official_run)
    messages = list(payload["messages"])
    tools = prepared["tool_objects"]
    state = set(prepared["state"])
    action = first["raw_tool_calls"][0]
    tool_name = action["name"]
    tool = tools[tool_name]
    if not set(tool.input_types).issubset(state):
        raise ValueError("Archived first action is no longer feasible")
    # Reuse exactly the archived first tool result; do not call the model for it again.
    call_id = "call_archived_first_action"
    messages.append({"role":"assistant","content":first.get("assistant_content"),
                     "tool_calls":[{"id":call_id,"type":"function","function":{
                         "name":tool_name,"arguments":action["arguments"]}}]})
    messages.append({"role":"tool","tool_call_id":call_id,"name":tool_name,
                     "content":first["tool_result"]})
    state.add(tool.output_type)
    path = [tool_name]
    trace = [{"step":1,"tool":tool_name,"cost":float(tool.cost),"success":True,
              "archived":True,"arguments":action["arguments"]}]
    extra_tokens = 0
    model_calls = 0
    halt = None
    for step in range(2, max_steps+1):
        if prepared["goal_type"] in state:
            halt = "goal_reached"
            break
        try:
            response = await native.call_model(client,messages,payload["tools"],
                                               "required",max_tokens,budget)
        except Exception as exc:
            halt = "api_error:" + str(exc)
            break
        model_calls += 1
        extra_tokens += int(response.usage.total_tokens)
        msg = response.choices[0].message
        messages.append(native.assistant_message_dict(msg))
        calls = msg.tool_calls or []
        if len(calls) != 1:
            halt = "no_or_multiple_tool_calls"
            break
        call = calls[0]
        name = call.function.name
        obj = tools.get(name)
        if obj is None or not set(obj.input_types).issubset(state):
            halt = "invalid_or_infeasible_tool"
            break
        try:
            result = official_run._execute_tool_simulation(
                tool_obj=obj,arguments_str=call.function.arguments,
                refinement_level=native.REFINEMENT_LEVEL,available_tools=tools)
            success = not (isinstance(result,str) and result.startswith(native.ERROR_PREFIXES))
        except Exception as exc:
            result = f"[ERROR] {type(exc).__name__}: {exc}"
            success = False
        messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":str(result)})
        path.append(name)
        trace.append({"step":step,"tool":name,"cost":float(obj.cost),
                      "success":success,"arguments":call.function.arguments,
                      "output":str(result)})
        if not success:
            halt = "tool_execution_error"
            break
        state.add(obj.output_type)
    if halt is None:
        halt = "goal_reached" if prepared["goal_type"] in state else "max_tool_steps"
    best, _, _ = optimal_first_actions(prepared)
    path_cost = sum(t["cost"] for t in trace)
    reached = prepared["goal_type"] in state
    return {
        "trial_id":trial["trial_id"],"query_id":trial["query_id"],
        "environment_condition":trial["environment_condition"],
        "prompt_condition":trial["prompt_condition"],
        "source_formal_first_action":first["trial_id"],
        "source_request_sha256":first["request_sha256"],
        "checkpoint_sha256":first["checkpoint_sha256"],
        "first_action":first["first_action"],"first_action_regret":first["first_action_regret"],
        "first_action_optimal":first["is_optimal_first_action"],
        "executed_path":path,"trace":trace,"goal_reached":reached,
        "halt_reason":halt,"path_cost":round(path_cost,8),
        "oracle_optimal_cost":round(best,8),
        "path_regret":round(max(0,path_cost-best),8) if reached else None,
        "full_incumbent_suffix":path==prepared["incumbent_suffix"],
        "continuation_model_calls":model_calls,
        "continuation_tokens":extra_tokens,
        "archived_first_action_tokens":first["provider_total_tokens"],
    }

async def run(chosen, official_run, args):
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY missing")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError("Output directory must be empty")
    args.out.mkdir(parents=True)
    client = official_run.AsyncOpenAI(base_url="https://api.deepseek.com",
                                     api_key=key,timeout=args.timeout)
    budget = native.TokenBudget(args.cap)
    results=[]
    try:
        for trial,first,_ in chosen:
            start=time.monotonic()
            row=await continue_one(trial,first,official_run,client,budget,
                                   args.max_tokens,args.max_steps)
            row["elapsed_seconds"]=round(time.monotonic()-start,3)
            results.append(row)
            append_jsonl(args.out/"continuations.jsonl",row)
            save_json(args.out/"ledger.json",{
                "completed":len(results),"planned":len(chosen),
                "continuation_tokens":budget.charged,"cap":args.cap})
            print(json.dumps({"completed":len(results),"total":len(chosen),
                              "trial_id":row["trial_id"],"goal_reached":row["goal_reached"],
                              "halt_reason":row["halt_reason"],
                              "continuation_tokens":budget.charged}),flush=True)
    finally:
        await client.close()
    summary={"status":"complete" if len(results)==16 else "partial",
             "trajectories":len(results),"goals_reached":sum(r["goal_reached"] for r in results),
             "continuation_tokens":budget.charged,"cap":args.cap,
             "per_cell":{}}
    for env in ("RETAIN","SWITCH"):
        for arm in ARMS:
            subset=[r for r in results if r["environment_condition"]==env
                    and r["prompt_condition"]==arm]
            summary["per_cell"][f"{env}/{arm}"]={
                "n":len(subset),"goals_reached":sum(r["goal_reached"] for r in subset),
                "mean_regret":(sum(r["path_regret"] for r in subset)/len(subset))
                if subset and all(r["path_regret"] is not None for r in subset) else None}
    save_json(args.out/"summary.json",summary)
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--data-dir",type=Path,default=HERE.parent/"generated")
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--out",type=Path,default=HERE/"continuation_results")
    p.add_argument("--live",action="store_true")
    p.add_argument("--cap",type=int,default=500000)
    p.add_argument("--max-tokens",type=int,default=2048)
    p.add_argument("--max-steps",type=int,default=12)
    p.add_argument("--timeout",type=int,default=120)
    args=p.parse_args()
    args.costbench_root=args.costbench_root.resolve()
    args.data_dir=args.data_dir.resolve()
    args.archive=args.archive.resolve()
    args.out=args.out.resolve()
    os.chdir(args.costbench_root)
    costbench=native.load_costbench(args.costbench_root)
    chosen=prepare(args.archive,costbench,args.data_dir)
    report={"status":"validated_no_provider_calls","trajectories":len(chosen),
            "task_ids":list(TASKS),"cells":sorted(x[0]["trial_id"] for x in chosen),
            "archived_first_actions_reused":len(chosen)}
    if not args.live:
        print(json.dumps(report,indent=2))
        return
    print(json.dumps(asyncio.run(run(chosen,costbench["official_run"],args)),indent=2))

if __name__=="__main__":
    main()
