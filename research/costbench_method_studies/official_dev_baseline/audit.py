#!/usr/bin/env python3
"""Audit all 160 planned official CostBench Agent rollouts; keep failures in denominators."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
import math

def strict_json(value):
    if isinstance(value,float):
        return value if math.isfinite(value) else None
    if isinstance(value,dict):
        return {k:strict_json(v) for k,v in value.items()}
    if isinstance(value,list):
        return [strict_json(v) for v in value]
    return value

CONDITIONS=("static","official_cost_change")
FILES={
 "static":"results_deepseek-flash_unblocked_refinement_2.json",
 "official_cost_change":"results_deepseek-flash_blocked-cost_change-1_refinement_2.json",
}
def summarize(root:Path):
    src=root/"inputs/manifest.json"
    manifest=json.loads(src.read_text(encoding="utf-8"))
    if manifest["upstream_commit"]!="6424069f3f773ade076bcedbed302ed47cfb1837":
        raise AssertionError("incorrect pinned official runtime")
    if manifest["population"]!={"development":80,"validation":40,"locked_test":80}:
        raise AssertionError("wrong frozen split")
    shards=manifest["shards"]
    if len(shards)!=4 or len({v for ids in shards.values() for v in ids})!=80:
        raise AssertionError("task partition changed")
    rows=[]
    groups={}
    raw_sha={}
    missing=[]
    for mode in CONDITIONS:
      for i in range(4):
        ids=shards[str(i)]
        path=root/"results"/mode/("shard%02d"%i)/FILES[mode]
        if not path.is_file():
            missing.append(str(path)); continue
        raw=path.read_bytes()
        if not raw:
            missing.append(str(path));continue
        doc=json.loads(raw)
        stats=doc.get("stats",{})
        if (stats.get("model_name")!="deepseek-flash"
            or stats.get("total_queries")!=20
            or stats.get("refinement_level")!=2
            or stats.get("max_tool_steps")!=7
            or stats.get("max_tokens")!=8192
            or stats.get("tool_creation_seed")!=42
            or not stats.get("ban_longest_tool")):
            raise AssertionError("official runner configuration drift: "+str(path))
        if bool(stats.get("use_blocker"))!=(mode!="static"):
            raise AssertionError("blocker mismatch: "+str(path))
        if mode!="static" and (stats.get("block_mode")!="cost_change" or stats.get("block_num")!=1):
            raise AssertionError("dynamic event protocol mismatch")
        data=doc.get("results")
        if not isinstance(data,list) or len(data)!=20:
            raise AssertionError("expected 20 result rows even if execution failed: "+str(path))
        got=[r.get("query_id","").strip("<>") for r in data]
        if set(got)!=set(ids) or len(set(got))!=20:
            raise AssertionError("missing/duplicate/wrong task in "+str(path))
        raw_sha[f"{mode}/shard{i:02d}"]=hashlib.sha256(raw).hexdigest()
        scores=stats.get("scores") or {}
        groups[f"{mode}/shard{i:02d}"]={
           "official_statistics":scores,
           "output_sha256":raw_sha[f"{mode}/shard{i:02d}"],
           "tasks":20}
        for row in data:
            qid=row["query_id"].strip("<>")
            history=row.get("conversation_history") or []
            native_calls=sum(len(m.get("tool_calls") or [])
                 for m in history if isinstance(m,dict) and m.get("role")=="assistant")
            assistant_messages=[m for m in history if isinstance(m,dict) and m.get("role")=="assistant"]
            ev=row.get("evaluation") or {}
            blocks=row.get("block_stats") or {}
            trigger=int(blocks.get("block_count_agent",0) or 0) if mode!="static" else 0
            pre_event_termination=None
            if mode!="static" and trigger==0:
                if len(assistant_messages)==0:
                    pre_event_termination="no_assistant_message_recorded"
                elif native_calls==0:
                    pre_event_termination="assistant_without_tool_or_final_answer"
                else:
                    pre_event_termination="tool_prefix_stopped_before_event"
            run={
                "query_id":qid,"condition":mode,
                "category":row.get("task"),
                "status":row.get("status","unknown"),
                "goal_state_reached":row.get("is_goal_state") is True,
                "official_final_answer_success":ev.get("success") is True,
                "official_evaluation_recorded":ev.get("success") in (True,False),
                "native_tool_calls_requested":native_calls,
                "assistant_messages_recorded":len(assistant_messages),
                "pre_event_termination":pre_event_termination,
                "native_tool_called":native_calls>0,
                "steps":row.get("total_steps"),
                "dynamic_events_triggered":trigger,
                "failure":row.get("error"),
                "source_file_key":f"{mode}/shard{i:02d}",
            }
            rows.append(run)
    if missing:
        raise FileNotFoundError("Missing raw official results: "+", ".join(missing))
    if len(rows)!=160 or len({(r["query_id"],r["condition"]) for r in rows})!=160:
        raise AssertionError("not exactly 160 distinct task-condition result rows")
    byid=defaultdict(dict)
    for row in rows:byid[row["query_id"]][row["condition"]]=row
    if len(byid)!=80 or any(set(x)!=set(CONDITIONS) for x in byid.values()):
        raise AssertionError("incomplete 80 task-pair coverage")
    per_condition={}
    for cond in CONDITIONS:
        v=[r for r in rows if r["condition"]==cond]
        valid=[r for r in v if r["official_evaluation_recorded"]]
        per_condition[cond]={
            "attempted_trajectories":len(v),
            "native_tool_called":sum(r["native_tool_called"] for r in v),
            "goal_state_reached":sum(r["goal_state_reached"] for r in v),
            "official_final_answer_success":sum(r["official_final_answer_success"] for r in v),
            "evaluation_recorded":len(valid),
            "no_native_tool_call":sum(not r["native_tool_called"] for r in v),
            "status_counts":dict(Counter(str(r["status"]) for r in v)),
            "dynamic_event_triggered":sum(r["dynamic_events_triggered"]>0 for r in v),
            "dynamic_event_not_triggered":sum(r["dynamic_events_triggered"]==0 for r in v) if cond!="static" else None,
            "pre_event_termination_types":dict(Counter(str(r["pre_event_termination"])
                for r in v if r["pre_event_termination"] is not None)),
        }
    both_success=sum(all(p[c]["official_final_answer_success"] for c in CONDITIONS) for p in byid.values())
    static_only=sum(p["static"]["official_final_answer_success"] and not p["official_cost_change"]["official_final_answer_success"] for p in byid.values())
    dynamic_only=sum(p["official_cost_change"]["official_final_answer_success"] and not p["static"]["official_final_answer_success"] for p in byid.values())
    report={
       "protocol":manifest["protocol"],
       "status":"160_original_official_harness_trajectories_audited",
       "independent_base_tasks":80,
       "correlated_task_condition_trajectories":len(rows),
       "model":"deepseek-flash",
       "methods_scope":"native official CostBench Agent baseline; no intervention-policy comparison",
       "per_condition":per_condition,
       "paired_task_outcomes":{
          "both_answers_correct":both_success,
          "static_only_correct":static_only,
          "dynamic_only_correct":dynamic_only,
          "neither_correct":80-both_success-static_only-dynamic_only,
       },
       "counts_by_category":{
          category:{"tasks":len({r["query_id"] for r in rows if r["category"]==category}),
                    "static_answer_success":sum(r["official_final_answer_success"] for r in rows if r["category"]==category and r["condition"]=="static"),
                    "dynamic_answer_success":sum(r["official_final_answer_success"] for r in rows if r["category"]==category and r["condition"]=="official_cost_change")}
          for category in sorted({str(r["category"]) for r in rows})
       },
       "provider_token_usage":None,
       "provider_cost_usd":None,
       "provider_latency_seconds":None,
       "caveats":[
         "Original official CostBench result JSON files do not provide per-task provider token/cost/latency records.",
         "The baseline is a reactive Agent without an explicit committed remaining plan.",
         "An observed tool-path change alone does not establish internal replanning.",
         "Static/dynamic results for the same base task are correlated.",
         "The official dynamic blocker can affect the reference continuation; reference state alignment requires a separate audit.",
         "No validation or locked-test queries were evaluated."
       ],
       "raw_sha256":raw_sha,"group_stats":groups,"rows":rows,
    }
    return strict_json(report)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=summarize(a.root.resolve())
    if a.out.exists():
        raise FileExistsError("do not overwrite completed result audit")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print("PHASE2_OFFICIAL_BASELINE_AUDIT "+
       json.dumps({"base_tasks":result["independent_base_tasks"],
         "trajectories":result["correlated_task_condition_trajectories"],
         "static":result["per_condition"]["static"],
         "dynamic":result["per_condition"]["official_cost_change"]},sort_keys=True))
