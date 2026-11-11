#!/usr/bin/env python3
"""Native full-trajectory pilot with the first action controlled fairly by policy.

The same DeepSeek Flash model generates arguments for the first selected tool
and all later tool calls. Each candidate arm starts from the same frozen
CostBench checkpoint, independently, under the same original plan-visible
context. No oracle scores enter any policy prompt or execution decision.

Dry-run is the default. --live requires DEEPSEEK_API_KEY and a token cap.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from pathlib import Path

import bounded_candidate_verifier as evidence
import graph_planning_baseline as classic
import run_bounded_verifier_confirmation as confirm
import run_four_arm_experiment as screen

HERE = Path(__file__).resolve().parent
COHORT = ("Query00178", "Query00351", "Query00549", "Query00689", "Query00851")
POLICIES = ("incumbent", "candidate_gate", "graph_planner")
MAX_TOOL_STEPS = 12


def load_policy_trials(costbench_root, archived_responses):
    source = [json.loads(s) for s in archived_responses.read_text(encoding="utf-8").splitlines() if s.strip()]
    trials, costbench = confirm.load_checkpoints(costbench_root)
    if len(source) != 20:
        raise ValueError("Expected 20 frozen confirmation candidate records")
    indexed = {r["trial_id"]:r for r in source}
    if len(indexed) != 20:
        raise ValueError("Duplicate confirmation trial IDs")
    chosen = []
    for trial in trials:
        if trial["query_id"] not in COHORT:
            continue
        if trial["trial_id"] not in indexed:
            raise ValueError("Missing frozen confirmation candidate")
        p, record = trial["prepared"], indexed[trial["trial_id"]]
        if record["checkpoint_sha256"] != p["checkpoint_sha256"] or record["source_trial_id"] != trial["source_trial_id"]:
            raise ValueError("Frozen candidate does not match checkpoint")
        candidate = record.get("first_action")
        if record.get("first_action_status") != "executed" or candidate not in p["tool_objects"]:
            raise ValueError("Invalid source candidate; stop without substitution")
        incumbent = p["incumbent_suffix"][0]
        gate = evidence.verify(p, incumbent, candidate)
        graph = classic.shortest_feasible_path(p)
        if graph is None:
            raise ValueError("No feasible graph continuation")
        choices = {
            "incumbent": incumbent,
            "candidate_gate": candidate if gate["decision"] == "ACCEPT" else incumbent,
            "graph_planner": graph[1][0],
        }
        visible = {x["function"]["name"] for x in p["tool_interfaces"]}
        for policy, name in choices.items():
            obj = p["tool_objects"][name]
            if name not in visible or not set(obj.input_types).issubset(set(p["state"])):
                raise ValueError("Policy selects unavailable or infeasible action")
            chosen.append({
                "trial": trial,
                "policy": policy,
                "first_action_name": name,
                "gate_decision": gate["decision"],
                "candidate": candidate,
                "graph_reference_path": graph[1],
            })
    if len(chosen) != 30 or len({x["trial"]["query_id"] for x in chosen}) != 5:
        raise ValueError("Expected five disjoint confirmation tasks and 30 policy paths")
    random.Random(731).shuffle(chosen)
    return chosen, costbench


def make_messages(prepared, official_run, tool_name):
    return [
        {"role":"system","content":screen.native.make_official_system_prompt(official_run,prepared["task"])},
        {"role":"user","content":screen.native.make_checkpoint_user_message(prepared)
         + "\n\n[Native action-control evaluation]\n"
         + "For this controlled comparison, your FIRST tool call must invoke "
         + tool_name + ". Use its actual required arguments based on the current "
         + "observation. After its result, choose subsequent actions freely "
         + "using the available current tools. This first-step restriction is "
         + "identical across all evaluated policies."},
    ]


async def run_one(item, cb, client, budget, max_tokens):
    trial = item["trial"]
    p = trial["prepared"]
    tool_name = item["first_action_name"]
    selected_schema = [x for x in p["tool_interfaces"] if x["function"]["name"] == tool_name]
    if len(selected_schema) != 1:
        raise ValueError("Selected action does not have one native interface")
    messages = make_messages(p, cb["official_run"],tool_name)
    state = set(p["state"])
    steps = []
    halt = None
    start = time.monotonic()
    for i in range(1,MAX_TOOL_STEPS+1):
        if p["goal_type"] in state:
            halt = "goal_reached"
            break
        available = selected_schema if i == 1 else p["tool_interfaces"]
        try:
            response = await screen.native.call_model(
                client, messages, available, "required", max_tokens, budget)
        except Exception as exc:
            halt = "model_error:" + str(exc)
            break
        msg = response.choices[0].message
        messages.append(screen.native.assistant_message_dict(msg))
        calls = msg.tool_calls or []
        if len(calls) != 1:
            halt = "invalid_tool_call_count"
            break
        call = calls[0]
        name, args = call.function.name, call.function.arguments
        tool = p["tool_objects"].get(name)
        if (i == 1 and name != tool_name) or tool is None or not set(tool.input_types).issubset(state):
            halt = "invalid_or_infeasible_action"
            break
        try:
            result = cb["official_run"]._execute_tool_simulation(
                tool_obj=tool, arguments_str=args,
                refinement_level=screen.native.REFINEMENT_LEVEL,
                available_tools=p["tool_objects"])
            success = not (isinstance(result,str) and result.startswith(screen.native.ERROR_PREFIXES))
        except Exception as exc:
            result = f"[ERROR] {type(exc).__name__}: {exc}"
            success = False
        messages.append({"role":"tool","name":name,"tool_call_id":call.id,"content":str(result)})
        steps.append({"tool":name,"arguments":args,"output":str(result),"success":success,
                      "cost":float(tool.cost),"provider_tokens":int(response.usage.total_tokens)})
        if not success:
            halt = "native_tool_error"
            break
        state.add(tool.output_type)
    if halt is None:
        halt = "goal_reached" if p["goal_type"] in state else "step_limit"
    reached = p["goal_type"] in state
    path = [x["tool"] for x in steps]
    reference_value, _, _ = screen.optimal_first_actions(p)
    path_value = sum(x["cost"] for x in steps)
    return {
        "query_id":trial["query_id"],
        "environment":trial["environment_condition"],
        "source_trial_id":trial["source_trial_id"],
        "checkpoint_sha256":p["checkpoint_sha256"],
        "policy":item["policy"],"controlled_first_action":tool_name,
        "candidate":item["candidate"],"gate_decision":item["gate_decision"],
        "reached_goal":reached,"halt_reason":halt,
        "path":path,"steps":steps,
        "path_value":round(path_value,8),
        "reference_value":round(reference_value,8),
        "path_regret":round(max(0.0,path_value-reference_value),8) if reached else None,
        "model_calls":sum(1 for x in steps) if halt not in ("invalid_tool_call_count",) else len(steps)+1,
        "provider_tokens":sum(x["provider_tokens"] for x in steps),
        "elapsed_seconds":round(time.monotonic()-start,3),
    }


def summarize(rows,planned):
    summary={"status":"complete" if len(rows)==planned and not any(r["halt_reason"].startswith("model_error") for r in rows) else "partial",
             "planned_paths":planned,"paths":len(rows),"per_policy":{}}
    for policy in POLICIES:
        rs=[r for r in rows if r["policy"]==policy]
        summary["per_policy"][policy]={
            "n":len(rs),
            "goals_reached":sum(r["reached_goal"] for r in rs),
            "goal_reach_rate":sum(r["reached_goal"] for r in rs)/len(rs) if rs else None,
            "exact_reference_paths":sum(r["reached_goal"] and r["path_regret"]<=1e-6 for r in rs),
            "mean_path_regret":sum(r["path_regret"] for r in rs if r["path_regret"] is not None)/
                sum(r["path_regret"] is not None for r in rs) if any(r["path_regret"] is not None for r in rs) else None,
            "tokens":sum(r["provider_tokens"] for r in rs),
        }
    return summary


async def execute(items,cb,args):
    from openai import AsyncOpenAI
    key=os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError("Destination must be empty for append-only run")
    args.out.mkdir(parents=True,exist_ok=True)
    budget=screen.native.TokenBudget(args.cap)
    rows=[]
    async with AsyncOpenAI(base_url="https://api.deepseek.com",api_key=key,timeout=args.timeout) as client:
        for item in items:
            r=await run_one(item,cb,client,budget,args.max_tokens)
            rows.append(r)
            screen.append_jsonl(args.out/"trajectories.jsonl",r)
            screen.save_json(args.out/"ledger.json",{"completed":len(rows),
                "planned":len(items),"charged":budget.charged,"cap":budget.cap})
            print(json.dumps({"finished":len(rows),"total":len(items),
                "task":r["query_id"],"policy":r["policy"],
                "goal":r["reached_goal"],"halt":r["halt_reason"],
                "tokens":budget.charged}),flush=True)
            if r["halt_reason"].startswith("model_error"):
                break
    report=summarize(rows,len(items))
    report["charged_tokens"]=budget.charged
    report["token_cap"]=budget.cap
    report["cohort"]=list(COHORT)
    screen.save_json(args.out/"summary.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root",required=True,type=Path)
    parser.add_argument("--confirmation-archive",required=True,type=Path)
    parser.add_argument("--out",type=Path,default=HERE/"full_path_pilot")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--cap",type=int,default=600000)
    parser.add_argument("--max-tokens",type=int,default=1024)
    parser.add_argument("--timeout",type=int,default=120)
    args=parser.parse_args()
    args.costbench_root=args.costbench_root.resolve()
    args.out=args.out.resolve()
    path=args.confirmation_archive.resolve()
    if path.is_dir():
        path=path/"responses.jsonl"
    items,cb=load_policy_trials(args.costbench_root,path)
    if not args.live:
        print(json.dumps({"status":"offline_frozen_preflight","planned_paths":len(items),
            "tasks":list(COHORT),"policy_arms":list(POLICIES),"provider_calls":0},indent=2))
        return
    result=asyncio.run(execute(items,cb,args))
    print(json.dumps(result,indent=2))
    if result["status"]!="complete":
        raise SystemExit(2)


if __name__=="__main__":
    main()
