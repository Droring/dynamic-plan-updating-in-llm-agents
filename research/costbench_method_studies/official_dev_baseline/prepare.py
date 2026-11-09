#!/usr/bin/env python3
"""Freeze 80 development queries for native official CostBench Agent evaluation.

Only data configuration. The Agent loop is the unmodified pinned CostBench env/run.py.
No validation or test task is processed, and this script never contacts an LLM.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
REGISTRY=ROOT/"research/costbench_method_studies/official_native_task_allocation/generated/candidate_registry.jsonl"
SOURCE_SHA="6424069f3f773ade076bcedbed302ed47cfb1837"
SHARDS=4
CONDITIONS=("static","official_cost_change")

def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",",":"))

def freeze(upstream:Path, out:Path):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("input manifest is immutable: do not overwrite "+str(out))
    import yaml
    registry_data=REGISTRY.read_bytes()
    rows=[json.loads(x) for x in registry_data.decode("utf-8").splitlines() if x.strip()]
    if len(rows)!=200 or len({x["query_id"] for x in rows})!=200:
        raise AssertionError("bad candidate registry")
    counts=Counter(x["split"] for x in rows)
    if counts!={"development":80,"validation":40,"locked_test":80}:
        raise AssertionError("changed frozen split membership")
    dev=[x for x in rows if x["split"]=="development"]
    if len(dev)!=80 or len({x["preference_sha256"] for x in dev})!=80:
        raise AssertionError("not 80 unique independent development signatures")
    source_path=upstream/"env/data/runtime/queries/queries.json"
    raw=source_path.read_bytes()
    all_queries=json.loads(raw)
    byid={q["query_id"].strip("<>"):q for q in all_queries}
    if len(byid)!=len(all_queries):
        raise AssertionError("duplicate CostBench query ID")
    out.mkdir(parents=True,exist_ok=True)
    config=yaml.safe_load((upstream/"env/config/travel_config.yaml").read_text(encoding="utf-8"))
    config["model"]["endpoints"]["deepseek-flash"]={
        "base_url":"https://api.deepseek.com", "api_key_env":"DEEPSEEK_API_KEY"}
    config["model"]["model_name"]="deepseek-flash"
    config["model"]["temperature"]=0.0
    config["model"]["max_tokens"]=8192
    (out/"official_deepseek_config.yaml").write_text(
        yaml.safe_dump(config,sort_keys=False),encoding="utf-8")
    shards={}
    hashes={}
    for n in range(SHARDS):
        group=dev[n*20:(n+1)*20]
        if len(group)!=20:
            raise AssertionError("unbalanced deterministic shard")
        queries=[]
        for row in group:
            q=byid.get(row["query_id"])
            if q is None:
                raise AssertionError("selected dev ID absent in official source")
            if hashlib.sha256(canonical(q).encode("utf-8")).hexdigest()!=row["source_query_sha256"]:
                raise AssertionError("upstream query contents drifted "+row["query_id"])
            if row["category"]!=q["task"]:
                raise AssertionError("category differs")
            queries.append(q)
            hashes[row["query_id"]]=row["source_query_sha256"]
        path=out/("shard%02d.json"%n)
        path.write_text(json.dumps(queries,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        shards[str(n)]=[row["query_id"] for row in group]
    result={
       "protocol":"phase2-official-costbench-dev80-static-vs-cost-change-v1",
       "execution":"pinned unmodified official env/run.py",
       "upstream_commit":SOURCE_SHA,
       "candidate_registry_sha256":hashlib.sha256(registry_data).hexdigest(),
       "upstream_queries_file_sha256":hashlib.sha256(raw).hexdigest(),
       "population":{"development":80,"validation":40,"locked_test":80},
       "independent_base_tasks":80,
       "planned_correlated_trajectories":160,
       "shards":shards,"source_query_sha256":hashes,
       "conditions":list(CONDITIONS),"model":"deepseek-flash",
       "temperature":0,"refinement_level":2,"max_tool_steps":7,"max_tokens":8192,
       "tool_creation_seed":42,"ban_longest_tool":True,"num_threads":2,
       "dynamic_block_mode":"cost_change","dynamic_block_num":1,
       "status":"frozen_before_paid_agent_rollouts",
       "observation":"This baseline uses the official reactive Agent, not a precommitted complete-plan intervention.",
    }
    (out/"manifest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    manifest=freeze(a.costbench_root.resolve(),a.out.resolve())
    print(json.dumps({"tasks":manifest["independent_base_tasks"],"conditions":manifest["conditions"],
                      "shards":len(manifest["shards"]),"split":manifest["population"]}))
