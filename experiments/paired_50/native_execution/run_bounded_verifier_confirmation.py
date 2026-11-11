#!/usr/bin/env python3
"""Run disjoint 10-task no-plan candidate generation and frozen bounded verification.

The verifier uses CURRENT native tools and a fixed four-step bounded graph
search, not official oracle values. Native solver is called only to score
selected actions. --live is required for model calls.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path

import bounded_candidate_verifier as evidence
import run_four_arm_experiment as screen

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "generated"
MANIFEST_PATH = HERE / "BOUNDED_VERIFIER_CONFIRMATION_MANIFEST.json"


def load_checkpoints(costbench_root):
    os.chdir(costbench_root)
    cohort = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cb = screen.native.load_costbench(costbench_root)
    if cb["revision"] != cohort["upstream_costbench_revision"]:
        raise ValueError("Pinned CostBench revision mismatch")
    requests, manifests, registry = screen.native.load_frozen_inputs(DATA_DIR)
    request_by_query = {}
    for request in requests:
        request_by_query.setdefault(request["query_id"], []).append(request)
    registry_by_query = {row["task_id"]: row for row in registry["selection"]["task_ids"]}
    queries_path = costbench_root / "env" / "data" / "runtime" / "queries" / "queries.json"
    native_queries = json.loads(queries_path.read_text(encoding="utf-8"))
    query_by_id = {q["query_id"].strip("<>"):q for q in native_queries}
    preselected = {r["query_id"] for r in cohort["tasks"]}
    if len(preselected) != 10 or preselected.intersection(cohort["excluded_development_tasks"]):
        raise ValueError("Confirmation tasks overlap mechanism development cohort")
    result = []
    for task in cohort["tasks"]:
        qid = task["query_id"]
        entries = request_by_query.get(qid, [])
        if len(entries) != 2:
            raise ValueError(f"Missing paired requests: {qid}")
        for request in entries:
            source = manifests[request["trial_id"]]
            if request["checkpoint_sha256"] != task["checkpoint_sha256"]:
                raise ValueError("Confirmation task checkpoint mismatch")
            prepared = screen.native.prepare_trial(
                request, source, query_by_id[qid],
                registry_by_query[qid], cb
            )
            if prepared["checkpoint_sha256"] != task["checkpoint_sha256"]:
                raise ValueError("Reconstructed checkpoint mismatch")
            result.append({
                "query_id": qid, "category": task["category"],
                "environment_condition": source["condition"],
                "prompt_condition": "C",
                "repetition": 1,
                "trial_id": f"{qid}_{source['condition']}_C_r1",
                "source_trial_id": request["trial_id"],
                "task": task, "request": request, "manifest_row": source,
                "prepared": prepared,
            })
    if len(result) != 20:
        raise ValueError("Expected 20 checkpoint actions")
    if {x["environment_condition"] for x in result} != {"RETAIN", "SWITCH"}:
        raise ValueError("Missing paired RETAIN/SWITCH")
    random.Random(20261111).shuffle(result)
    return result, cb


def score(trials, recorded):
    if len(recorded) != 20:
        raise ValueError("Cannot grade incomplete candidate generation")
    by_id = {r["trial_id"]:r for r in recorded}
    if len(by_id) != 20:
        raise ValueError("Duplicate model trial identifier")
    if set(by_id) != {trial["trial_id"] for trial in trials}:
        raise ValueError("Model trial IDs differ from the frozen confirmation manifest")
    rows = []
    for trial in trials:
        p = trial["prepared"]
        r = by_id[trial["trial_id"]]
        if r["source_trial_id"] != trial["source_trial_id"]:
            raise ValueError("Frozen request mismatch")
        if r["checkpoint_sha256"] != p["checkpoint_sha256"]:
            raise ValueError("Candidate checkpoint mismatch")
        old = p["incumbent_suffix"][0]
        proposal = r.get("first_action")
        valid = r.get("first_action_status") == "executed"
        if not valid:
            proposal = old
        verdict = evidence.verify(p, old, proposal)
        selected = proposal if verdict["decision"] == "ACCEPT" else old
        # Oracle scoring is strictly post-decision and not in the verifier.
        _, values, optimal = screen.optimal_first_actions(p)
        rows.append({
            "query_id": trial["query_id"],
            "environment": trial["environment_condition"],
            "trial_id": trial["trial_id"],
            "archived_source_trial_id": r["source_trial_id"],
            "candidate_executed": valid,
            "incumbent": old, "candidate": proposal,
            "verdict": verdict, "selected": selected,
            "selected_is_optimal": selected in optimal,
            "candidate_is_optimal": proposal in optimal,
            "incumbent_is_optimal": old in optimal,
        })
    def aggregate(env):
        a = [x for x in rows if x["environment"] == env]
        return {
            "trials": len(a),
            "incumbent_correct": sum(x["incumbent_is_optimal"] for x in a),
            "ungated_candidate_correct": sum(x["candidate_is_optimal"] for x in a),
            "gate_correct": sum(x["selected_is_optimal"] for x in a),
            "gate_accepted": sum(x["verdict"]["decision"]=="ACCEPT" for x in a),
            "invalid_candidate_calls": sum(not x["candidate_executed"] for x in a),
        }
    retain, switch = aggregate("RETAIN"), aggregate("SWITCH")
    return {
        "status": "completed_offline_scoring",
        "task_count": 10,
        "model_first_action_calls": 20,
        "model": screen.native.MODEL,
        "gate_used_oracle": False,
        "oracle_used_only_for_posthoc_scoring": True,
        "retained_task_count": 10,
        "RETAIN": retain, "SWITCH": switch,
        "baseline_incumbent_balanced_accuracy": (
            retain["incumbent_correct"]/10 + switch["incumbent_correct"]/10
        )/2,
        "candidate_only_balanced_accuracy": (
            retain["ungated_candidate_correct"]/10 + switch["ungated_candidate_correct"]/10
        )/2,
        "gated_balanced_accuracy": (
            retain["gate_correct"]/10 + switch["gate_correct"]/10
        )/2,
        "records": sorted(rows, key=lambda x:(x["query_id"],x["environment"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=HERE / "bounded_confirmation_results")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--score-from", type=Path)
    parser.add_argument("--cap", type=int, default=350000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=2048)
    args = parser.parse_args()
    args.costbench_root = args.costbench_root.resolve()
    args.out = args.out.resolve()
    trials, cb = load_checkpoints(args.costbench_root)
    if args.score_from:
        path = args.score_from.resolve()
        records = [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]
        result = score(trials, records)
        screen.save_json(args.out / "verification_results.json", result)
        print(json.dumps({k:v for k,v in result.items() if k!="records"}, indent=2))
        return
    audit = screen.offline_audit(trials, cb["official_run"], args.max_tokens)
    audit.update({
        "confirmation_base_tasks":10,
        "trials":20,
        "frozen_selection":str(MANIFEST_PATH.relative_to(HERE)),
        "method":"plan-omitted C candidate followed by bounded certificate",
        "no_oracle_in_candidate_prompt":True,
    })
    if not args.live:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("Missing DEEPSEEK_API_KEY")
    result = asyncio.run(screen.run_live(trials,cb["official_run"],args))
    if result["status"] != "complete":
        raise SystemExit(2)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
