#!/usr/bin/env python3
"""Inspect ONLY the 25-development-task graph for phase-2 method feasibility.

Does not touch validation/test graph states or labels. The CostBench graph
contains abstract tool dependencies, not model-committed native execution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[3]
SOURCE_REL="env/data/runtime/queries/queries.json"
sys.path.insert(0,str(HERE))
from build_registry import UPSTREAM_COMMIT,canonical,digest


def read_registry():
    rows=[json.loads(s) for s in (HERE/"generated/candidate_registry.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    if len(rows)!=200 or len({r["query_id"] for r in rows})!=200:
        raise ValueError("missing or repeated candidate registry")
    return rows


def inspect(root):
    rows=read_registry()
    dev=[r for r in rows if r["split"]=="development"]
    if len(dev)!=25:
        raise ValueError("expected 25 predeclared development candidates")
    source_path=root/SOURCE_REL
    report=json.loads((HERE/"generated/SCREENING_REPORT.json").read_text(encoding="utf-8"))
    if hashlib.sha256(source_path.read_bytes()).hexdigest()!=report["source_sha256"]:
        raise ValueError("pinned upstream source file differs")
    queries=json.loads(source_path.read_text(encoding="utf-8"))
    by_id={q["query_id"].strip("<>"):q for q in queries}
    sys.path.insert(0,str(root))
    from env.domains.travel.tool_registry import tools_ready_in_memory
    from env.utils.solver import GroundtruthSolver
    previous=Path.cwd()
    items=[]
    try:
        # Upstream tool registry uses relative runtime paths.
        os.chdir(root)
        for candidate in dev:
            q=by_id[candidate["query_id"]]
            if digest(q)!=candidate["source_query_sha256"]:
                raise ValueError("development query hash changed")
            task=q["task"]
            seed=200000+int(candidate["query_id"].replace("Query",""))
            snapshot=tools_ready_in_memory(refinement_level=2,
                        ban_longest_tool=True,random_seed=seed)["tools"]
            # Match the original heldout generator's registered tool scope:
            # all 5 travel categories have a disjoint type system.
            solver=GroundtruthSolver(snapshot)
            initial=set(solver._infer_initial_state(task))
            record={
               "query_id":candidate["query_id"],"category":task,
               "tool_count":len(snapshot),
               "graph_path_exists":False,
               "initial_optimal_length":None,
               "post_one_step_suffix_length":None,
               "alternative_after_one_tool_disabled":None,
               "local_repair_scope_with_nonempty_tail":False,
               "native_execution_verified":False,
               "failure":None
            }
            try:
                original=solver.solve(current_state=set(initial),goal_types={q["goal_type"]})
                plan=list(original.tools)
                record["graph_path_exists"]=True
                record["initial_optimal_length"]=len(plan)
                if len(plan)>=2:
                    after=initial|{snapshot[plan[0]]["output_type"]}
                    remaining=plan[1:]
                    record["post_one_step_suffix_length"]=len(remaining)
                    # Condition after one *abstract* tool step, not a native call.
                    if remaining:
                        banned=remaining[0]
                        alt={k:v for k,v in snapshot.items() if k!=banned}
                        try:
                            recovered=GroundtruthSolver(alt).solve(current_state=after,goal_types={q["goal_type"]})
                            record["alternative_after_one_tool_disabled"]=True
                            alternative=list(recovered.tools)
                            # A genuine local patch must rejoin a nonempty
                            # original tail and replace at least one action.
                            record["local_repair_scope_with_nonempty_tail"]=(
                                len(remaining)>=2 and alternative!=remaining
                                and any(alternative[-n:]==remaining[-n:]
                                        for n in range(1,len(remaining))))
                        except Exception as exc:
                            if type(exc).__name__=="NoPathFoundError":
                                record["alternative_after_one_tool_disabled"]=False
                            else:
                                raise
            except Exception as exc:
                if type(exc).__name__=="NoPathFoundError":
                    record["failure"]="no_initial_path"
                else:
                    raise
            items.append(record)
    finally:
        os.chdir(previous)
    return {
      "status":"development_graph_feasibility_not_live_model_execution",
      "screen_version":"phase2-dev-graph-gate-v1",
      "upstream_commit":UPSTREAM_COMMIT,
      "development_candidates":len(dev),
      "validation_and_test_queries_inspected":0,
      "model_calls":0,
      "counts":{
        "graph_path_exists":sum(x["graph_path_exists"] for x in items),
        "initial_path_length_distribution":dict(Counter(
            str(x["initial_optimal_length"]) for x in items)),
        "post_first_tool_remaining_steps":dict(Counter(
            str(x["post_one_step_suffix_length"]) for x in items)),
        "alternative_after_disabled":dict(Counter(
            str(x["alternative_after_one_tool_disabled"]) for x in items)),
        "local_repair_scope":sum(x["local_repair_scope_with_nonempty_tail"] for x in items)
      },
      "interpretation":"A solver-derived type graph is insufficient to certify native executed checkpoint or LLM plan commitment.",
      "development_cases":items
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--costbench-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=HERE/"generated/DEV_GRAPH_GATE.json")
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    result=inspect(args.costbench_root.resolve())
    content=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.check:
        if not args.out.is_file() or args.out.read_text(encoding="utf-8")!=content:
            raise SystemExit("development gate changed")
    else:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(content,encoding="utf-8")
    print("COSTBENCH_DEV_GRAPH "+json.dumps({
      "status":result["status"],"candidates":result["development_candidates"],
      "counts":result["counts"],"test_read":False,"model_calls":0},sort_keys=True))


if __name__=="__main__":
    main()
