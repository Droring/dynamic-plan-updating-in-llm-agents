#!/usr/bin/env python3
"""Validate generated pairs, serialized requests, and source checkpoint assumptions."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from generate_heldout import UPSTREAM_SHA, CATEGORIES, check_pair, create_request, pure_dijkstra, cost_variant, EPS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--costbench-root",type=Path,required=True)
    parser.add_argument("--dir",type=Path,default=Path(__file__).resolve().parent/"generated")
    args=parser.parse_args()
    sys.path.insert(0,str(args.costbench_root.resolve()))
    from env.utils.solver import GroundtruthSolver

    data=json.loads((args.dir/"pairs.json").read_text(encoding="utf-8"))
    pairs=data["pairs"]
    assert data["upstream_sha"] == UPSTREAM_SHA
    assert len(pairs)==15
    assert len({q["query_id"] for q in pairs})==15
    assert Counter(q["task"] for q in pairs)==Counter({k:3 for k in CATEGORIES})
    assert Counter(q["price_direction"] for q in pairs)==Counter({"up":8,"down":7})
    assert all(q["incumbent_source"]=="CostBench_oracle_not_model_precommit" for q in pairs)

    requests=[json.loads(x) for x in (args.dir/"model_requests.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    assert len(requests)==30
    assert all("condition" not in req and "oracle_cost" not in req for req in requests)
    lookup={q["trial_id"]:q for q in requests}
    assert len(lookup)==30
    manifest=json.loads((args.dir/"trial_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest)==30
    assert Counter(x["condition"] for x in manifest)==Counter({"RETAIN":15,"SWITCH":15})
    assert Counter(manifest[i]["condition"] for i in range(0,30,2))==Counter({"RETAIN":8,"SWITCH":7})
    from generate_heldout import sha
    for row in manifest:
        assert row["trial_id"] in lookup
        assert row["request_sha256"]==sha(lookup[row["trial_id"]])
    PRIOR_IDS = set(["Query00227","Query00236","Query00238","Query00240","Query00312","Query00329","Query00347","Query00351","Query00440","Query00466","Query00489","Query00494","Query00518","Query00590","Query00598","Query00610","Query00624","Query00662","Query00685","Query00689","Query00706","Query00761","Query00766","Query00798","Query00851","Query00858","Query00867","Query00916","Query00941","Query00944"])
    assert not {p["query_id"] for p in pairs} & PRIOR_IDS, "overlaps earlier 30-task study"
    for p in pairs:
        check_pair(p,GroundtruthSolver)
        for label in ("RETAIN","SWITCH"):
            expected=create_request(p,label)
            saved=lookup[expected["trial_id"]]
            assert saved==expected, "model-visible request differs from frozen generation"
            assert "oracle_cost" not in saved["messages"][-1]["content"]
            assert "regret" not in saved["messages"][-1]["content"]
            exposed=json.loads(saved["messages"][-1]["content"])
            full=cost_variant(p["baseline_tools"],p["changed_tool"],
                              next(x["changed_price"] for x in p["conditions"] if x["name"]==label))
            check_visible=pure_dijkstra(exposed["current_tools"],p["checkpoint"]["types"],p["goal_type"])
            check_full=pure_dijkstra(full,p["checkpoint"]["types"],p["goal_type"])
            assert check_visible is not None and check_full is not None
            assert abs(check_visible-check_full)<=EPS, "prompt omitted an optimal alternative"
    report=json.loads((args.dir/"REPORT.json").read_text(encoding="utf-8"))
    assert report["model_calls"]==0 and report["base_tasks"]==15
    print("VERIFIED: 15 previously unused tasks, 30 requests, paired checkpoint equivalence, "
          "native/Decimal agreement, no oracle-label leakage, no model calls.")


if __name__=="__main__":
    main()
