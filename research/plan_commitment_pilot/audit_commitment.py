#!/usr/bin/env python3
"""Offline lexical screen for EXISTING official CostBench development histories.
This never calls a model. Matches are NOT confirmed plan commitments.
"""
import argparse
import json
import re
from pathlib import Path

BROAD=re.compile(r"\b(?:then|followed by|after that|next|remaining|sequence|plan|I'll use|I will use|proceed)\b",re.I)
STRICT=re.compile(r"\b(?:then\s+(?:the|I|I'll|we|use|call|run|select|choose)|followed by|next\s+(?:I'll|I will|I|step|tool|use|call)|(?:I will|I'll|I plan to)\s+(?:use|call|run).{1,120}(?:then|next|followed))\b",re.I)
FILE="results_deepseek-flash_blocked-cost_change-1_refinement_2.json"

def audit(root):
    rows=[];seen=set()
    for i in range(4):
        path=root/"results"/"official_cost_change"/f"shard{i:02d}"/FILE
        doc=json.loads(path.read_text(encoding="utf-8"))
        for task in doc["results"]:
            qid=task["query_id"].strip("<>")
            if qid in seen:raise AssertionError("duplicate task "+qid)
            seen.add(qid)
            bs=task.get("block_stats") or {}
            k=(bs.get("block_step") or [None])[0]
            history=[m for m in task.get("conversation_history",[]) if m.get("role")=="assistant"]
            before=history[:k] if isinstance(k,int) and k>0 else []
            text="\n".join(m.get("content") or "" for m in before)
            rows.append({"query_id":qid,"event_observed":bs.get("block_count_agent")==1,
                "prefix_steps":k,"prefix_native_tool_calls":sum(len(m.get("tool_calls") or []) for m in before),
                "pre_event_text_present":bool(text.strip()),
                "broad_lexical_candidate":bool(BROAD.search(text)),
                "strict_lexical_candidate":bool(STRICT.search(text)),
                "semantically_verified_plan":None})
    if len(rows)!=80:raise AssertionError("expected 80 development tasks")
    observed=[x for x in rows if x["event_observed"]]
    if len(observed)!=67:raise AssertionError("observed-event denominator changed")
    counts={"base_tasks":len(rows),"event_observed":len(observed),
            "pre_event_native_tool_calls":sum(x["prefix_native_tool_calls"]>0 for x in observed),
            "pre_event_text":sum(x["pre_event_text_present"] for x in observed),
            "broad_lexical_candidates":sum(x["broad_lexical_candidate"] for x in observed),
            "strict_lexical_candidates":sum(x["strict_lexical_candidate"] for x in observed)}
    return {"schema":"plan-commitment-lexical-screen-v1","new_model_calls":0,
        "new_native_agent_trajectories":0,"counts":counts,
        "strict_candidate_ids":[x["query_id"] for x in rows if x["event_observed"] and x["strict_lexical_candidate"]],
        "rows":sorted(rows,key=lambda x:x["query_id"]),
        "warning":"Regex-only candidate screen, NOT a verified self-authored prospective plan or causal effect."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-root",type=Path,default=Path("research/costbench_method_studies/official_dev_baseline/evidence"))
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    data=audit(args.evidence_root)
    if args.out:
        if args.out.exists():raise FileExistsError("do not overwrite output")
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"counts":data["counts"],"strict_candidate_ids":data["strict_candidate_ids"]},sort_keys=True))
