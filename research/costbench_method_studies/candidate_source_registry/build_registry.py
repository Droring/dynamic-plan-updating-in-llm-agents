#!/usr/bin/env python3
"""Prospective task-ID/preference screening for the phase-2 evaluation.

Screening is entirely independent of outcome labels, graph solver performance,
model responses, or future policy accuracy. It only reads upstream query
metadata and the frozen historic exclusions. No model/API calls.

A selected row is a CANDIDATE, not yet an executable replanning case.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
UPSTREAM_COMMIT="6424069f3f773ade076bcedbed302ed47cfb1837"
SOURCE_REL="env/data/runtime/queries/queries.json"
SEED="phase2-unified-v1-20261106"
CATEGORIES=("transportation","accommodation","attraction","dining","shopping")
# Distinct *preference configurations* per category; 25 dev, 50 validation,
# 125 locked test, with 15 additional unseen signatures left in reserve.
QUOTAS={
    "transportation":{"development":7,"validation":15,"locked_test":38},
    "accommodation":{"development":3,"validation":7,"locked_test":17},
    "attraction":{"development":3,"validation":7,"locked_test":19},
    "dining":{"development":5,"validation":9,"locked_test":23},
    "shopping":{"development":7,"validation":12,"locked_test":28},
}
SPLITS=("development","validation","locked_test")


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def old_exclusions():
    """Read historic exclusions from the original generator, not a memory list."""
    manifests=(
      ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated/trial_manifest.json",
      ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_b/generated/trial_manifest.json",
    )
    ids=set()
    for p in manifests:
        rows=json.loads(p.read_text(encoding="utf-8"))
        ids.update(m["query_id"].strip("<>") for m in rows)
    if len(ids)!=45:
        raise ValueError("expected exactly 45 historic base task IDs")
    path=ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_b/generate_heldout.py"
    code=ast.parse(path.read_text(encoding="utf-8"))
    earlier=None
    for expr in code.body:
        if isinstance(expr,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id=="EXCLUDED" for t in expr.targets):
            earlier=ast.literal_eval(expr.value)
    if earlier is None or not isinstance(earlier,set):
        raise ValueError("historic pilot exclusions unavailable")
    ids.update(f"Query{i:05d}" for i in earlier)
    return ids


def preference_signature(query):
    if not isinstance(query.get("preferences"),dict) or not query["preferences"]:
        raise ValueError("query lacks structured preferences")
    return query["task"]+":"+canonical(query["preferences"])


def create(source, forbidden_ids, quotas=QUOTAS):
    if len(source)!=len({q["query_id"] for q in source}):
        raise ValueError("duplicate upstream query IDs")
    if len(forbidden_ids)<45:
        raise ValueError("historic exclusions unexpectedly incomplete")
    classes=defaultdict(list)
    historically_used_signatures=set()
    for q in source:
        if q.get("task") not in CATEGORIES or q.get("is_valid")!=1:
            continue
        signature=preference_signature(q)
        qid=q["query_id"].strip("<>")
        if qid in forbidden_ids:
            historically_used_signatures.add(signature)
        else:
            classes[signature].append(q)
    eligible={}
    for cat in CATEGORIES:
        sigs=[sig for sig in classes if sig.startswith(cat+":")
              and sig not in historically_used_signatures]
        sigs.sort(key=lambda sig:(hashlib.sha256((SEED+"|"+sig).encode()).hexdigest(),sig))
        required=sum(quotas[cat].values())
        if len(sigs)<required:
            raise ValueError(f"{cat}: only {len(sigs)} novel preference configurations, need {required}")
        eligible[cat]=sigs
    selected=[]
    for cat in CATEGORIES:
        cursor=0
        for split in SPLITS:
            amount=quotas[cat][split]
            for sig in eligible[cat][cursor:cursor+amount]:
                # Select one canonical query ID within the preference group,
                # independent of any labels, oracle path, or model responses.
                candidates=sorted(classes[sig],key=lambda q:q["query_id"])
                q=candidates[0]
                selected.append({
                    "query_id":q["query_id"].strip("<>"),
                    "category":cat,
                    "split":split,
                    "preference_sha256":hashlib.sha256(sig.encode("utf-8")).hexdigest(),
                    "source_query_sha256":digest(q),
                })
            cursor+=amount
    # A locked split's membership is determined entirely by static metadata.
    if len(selected)!=len({r["query_id"] for r in selected}):
        raise AssertionError("duplicate task IDs in selection")
    if len(selected)!=len({(r["category"],r["preference_sha256"]) for r in selected}):
        raise AssertionError("same structural preference repeated across splits")
    if forbidden_ids & {r["query_id"] for r in selected}:
        raise AssertionError("historical task leaks into new cohort")
    counts=Counter(r["split"] for r in selected)
    if dict(counts)!={"development":25,"validation":50,"locked_test":125} and quotas==QUOTAS:
        raise AssertionError("wrong split size")
    return selected,{
        "eligible_preference_signatures":{cat:len(eligible[cat]) for cat in CATEGORIES},
        "selected_by_category":dict(Counter(r["category"] for r in selected)),
        "selected_by_split":dict(counts),
        "reserve_signatures":{cat:len(eligible[cat])-sum(quotas[cat].values()) for cat in CATEGORIES},
    }


def build(costbench_root):
    path=costbench_root/SOURCE_REL
    source=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source,list):
        raise ValueError("upstream queries file is not an array")
    forbidden=old_exclusions()
    selected,stats=create(source,forbidden)
    report={
       "status":"candidate_registry_only_graph_and_native_execution_not_yet_qualified",
       "protocol":"phase2-unified-candidate-screen-v1",
       "selection_seed":SEED,
       "upstream_repo":"JiayuJeff/CostBench",
       "upstream_commit":UPSTREAM_COMMIT,
       "source_path":SOURCE_REL,
       "source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
       "all_source_queries":len(source),
       "source_five_category_queries":sum(
           q.get("task") in CATEGORIES and q.get("is_valid")==1 for q in source),
       "historic_excluded_query_ids":len(forbidden),
       "historic_original_base_tasks":45,
       "candidate_tasks":len(selected),
       "candidate_registry_sha256":digest(selected),
       "counts":stats,
       "split_rule":"category-stratified deterministic SHA ranking; one ID per distinct preference configuration",
       "eligibility_rule":"valid upstream five-category query; exclude 45 pilot tasks, historical probes and their preference configurations",
       "no_gold_labels_created":True,
       "no_graph_feasibility_claimed":True,
       "no_model_calls":True,
       "limitations":[
           "Query IDs and preference structures are a stronger anti-duplication check, not proof of statistically independent real-world problems.",
           "Preference templates are still generated within one CostBench domain.",
           "Test IDs are committed for provenance, but their scenario labels and online outcomes have not been created or inspected.",
           "Task IDs that fail graph or native-tool gates require a preregistered replacement procedure; do not silently reuse validation/test results."
       ]
    }
    return selected,report


def save(rows,report,out,check=False):
    out.mkdir(parents=True,exist_ok=True)
    content="".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows)
    summary=json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    target=out/"candidate_registry.jsonl"
    desc=out/"SCREENING_REPORT.json"
    if check:
        if not target.is_file() or not desc.is_file():
            raise ValueError("frozen candidate registry not found")
        if target.read_text(encoding="utf-8")!=content or desc.read_text(encoding="utf-8")!=summary:
            raise ValueError("candidate registry or provenance differs from deterministic source")
    else:
        target.write_text(content,encoding="utf-8")
        desc.write_text(summary,encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--costbench-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=HERE/"generated")
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    rows,report=build(args.costbench_root.resolve())
    save(rows,report,args.out,check=args.check)
    print("COSTBENCH_CANDIDATES "+json.dumps({
        "status":report["status"],"source_queries":report["all_source_queries"],
        "source_five_categories":report["source_five_category_queries"],
        "selected":report["candidate_tasks"],
        "split":report["counts"]["selected_by_split"],
        "novel_preference_signatures":report["counts"]["eligible_preference_signatures"],
        "reserve":report["counts"]["reserve_signatures"],"model_calls":0},
        sort_keys=True))


if __name__=="__main__":
    main()
