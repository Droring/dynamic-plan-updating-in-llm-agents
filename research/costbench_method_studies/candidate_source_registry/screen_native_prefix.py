#!/usr/bin/env python3
"""Native simulator smoke for ONE phase-2 development query per category.

No provider API. Argument values come only from the official CostBench query.
This is a native first-tool compatibility gate, not a completed LLM rollout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from build_registry import CATEGORIES,digest

def load_upstream(checkout):
    sys.path.insert(0,str(checkout.resolve()))
    from env.domains.travel.tool_registry import tools_ready_in_memory
    from env.core.base_types import create_tool_from_dict
    from env.core.data_types import get_final_type
    from env.utils.solver import GroundtruthSolver
    return tools_ready_in_memory,create_tool_from_dict,get_final_type,GroundtruthSolver

def build_tools(generator,converter,seed,task):
    snapshot=generator(refinement_level=2,min_atomic_cost=15,max_atomic_cost=25,
                       noise_std=.1,random_seed=seed,ban_longest_tool=True)
    relevant={name:attrs for name,attrs in snapshot["tools"].items()
              if task.capitalize() in name}
    if not relevant:
        raise ValueError("official CostBench tools absent for "+task)
    return {name:converter({**attrs,"name":name}) for name,attrs in relevant.items()}


def make_arguments(tool,q):
    values={}
    name=q["task"].capitalize()
    fields={"Category":"category","Tier":"tier",
            "Style":"style","FeaturePackage":"feature_package"}
    for t in tool.input_types:
        if t=="TimeInfo":
            values[t]=q["TimeInfo"]
        elif t=="LocationPreference":
            values[t]=q["location_preference"]
        elif t.startswith(name) and t[len(name):] in fields:
            values[t]=q["preferences"][fields[t[len(name):]]]
        else:
            raise ValueError("unsupported native first-tool argument type: "+t)
    return values


def execute(costbench_root,all_development=False):
    root=costbench_root.resolve()
    data=json.loads((root/"env/data/runtime/queries/queries.json").read_text(encoding="utf-8"))
    lookup={q["query_id"].strip("<>"):q for q in data}
    candidates=[json.loads(s) for s in (HERE/"generated/candidate_registry.jsonl").read_text(
        encoding="utf-8").splitlines() if s]
    dev=[r for r in candidates if r["split"]=="development"]
    selected=dev if all_development else [next(r for r in dev if r["category"]==cat) for cat in CATEGORIES]
    toolgen,converter,final_type,solvercls=load_upstream(root)
    original=Path.cwd()
    results=[]
    try:
        os.chdir(root)
        for entry in selected:
            q=lookup[entry["query_id"]]
            if digest(q)!=entry["source_query_sha256"]:
                raise ValueError("upstream source changed")
            seed=200000+int(entry["query_id"].replace("Query",""))
            tools=build_tools(toolgen,converter,seed,q["task"])
            solver=solvercls(tools)
            state=set(solver._infer_initial_state(q["task"]))
            initial=solver.solve(current_state=state,goal_types={q["goal_type"]})
            plan=list(initial.tools)
            if len(plan)<2:
                raise ValueError("no post-prefix replanning checkpoint")
            t=tools[plan[0]]
            try:
                params=make_arguments(t,q)
                raw=json.dumps(params,ensure_ascii=False)
                decoded=t.process_input(raw)
                executed=t.execute(input_data=decoded,available_tools=tools)
                output=t.process_output(tool_output=executed,refinement_level=2,
                                        available_tools=tools)
                ok=isinstance(output,str) and not output.startswith(
                    ("[ERROR]","Tool execution failed","Error:"))
                actual={"success":ok,"reason":None if ok else "native_tool_error",
                        "output":output if isinstance(output,str) else str(output),
                        "output_type":t.output_type if ok else None}
            except Exception as exc:
                actual={"success":False,"reason":type(exc).__name__+": "+str(exc)[:180]}
            results.append({
                "query_id":entry["query_id"],"task":q["task"],
                "tool_count":len(tools),"initial_plan_length":len(plan),
                "executed_first_tool":t.name,
                "first_tool_input_types":list(t.input_types),
                "native_success":bool(actual["success"]),
                "failure_reason":actual.get("reason"),
                "checkpoint_output_type":actual.get("output_type") if actual["success"] else None,
                "checkpoint_observation_sha256":hashlib.sha256((actual.get("output") or "").encode()).hexdigest()
                      if actual["success"] else None,
            })
    finally:
        os.chdir(original)
    return {
        "status":"native_first_tool_development_smoke_not_model_trajectory",
        "development_tasks":len(results),"provider_calls":0,
        "validation_and_test_tasks_executed":0,
        "native_prefix_success":sum(r["native_success"] for r in results),
        "cases":results
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--costbench-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=HERE/"generated/DEV_NATIVE_GATE.json")
    ap.add_argument("--check",action="store_true")
    ap.add_argument("--all-development",action="store_true",help="Execute 25 development native prefixes, no model calls")
    args=ap.parse_args()
    result=execute(args.costbench_root,args.all_development)
    payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.check:
        if args.out.read_text(encoding="utf-8")!=payload:
            raise ValueError("native execution gate changed")
    else:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(payload,encoding="utf-8")
    print("COSTBENCH_NATIVE_PREFIX "+json.dumps({
        "development_tasks":result["development_tasks"],
        "native_success":result["native_prefix_success"],
        "no_model_calls":True
    },sort_keys=True))
    return 0 if args.all_development or result["native_prefix_success"]==len(result["cases"]) else 2


if __name__=="__main__":
    raise SystemExit(main())
