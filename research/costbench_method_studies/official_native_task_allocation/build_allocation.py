#!/usr/bin/env python3
"""Create the documented 80/40/80 allocation from the sealed CostBench candidate registry.

No upstream task inspection, graph search, model calls, or label access occurs.
The 25 already-examined development tasks remain in development.

The frozen source-registry partition is preserved as provenance; this script builds the official native run allocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "research/costbench_method_studies/candidate_source_registry/generated"
SEED = "phase2-v2-80-40-80-stratified-transition"  # frozen allocation seed; not a study/version label
CATEGORIES = ("transportation", "accommodation", "attraction", "dining", "shopping")
SPLITS = ("development", "validation", "locked_test")
# A controlled revision of the existing 200 selected tasks. Keep as many
# original validation/test assignments as possible; never use observed labels.
TARGET = {
    "transportation": {"development": 24, "validation": 12, "locked_test": 24},
    "accommodation": {"development": 11, "validation": 5, "locked_test": 11},
    "attraction": {"development": 12, "validation": 6, "locked_test": 11},
    "dining": {"development": 15, "validation": 7, "locked_test": 15},
    "shopping": {"development": 18, "validation": 10, "locked_test": 19},
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def input_registry():
    raw = (SOURCE / "candidate_registry.jsonl").read_bytes()
    prior_report_raw = (SOURCE / "SCREENING_REPORT.json").read_bytes()
    old = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    screening = json.loads(prior_report_raw)
    if len(old) != 200 or len({x["query_id"] for x in old}) != 200:
        raise ValueError("initial registry missing or not unique")
    if len({x["preference_sha256"] for x in old}) != 200:
        raise ValueError("initial registry has duplicate preference configurations")
    if sha(canonical(old).encode("utf-8")) != screening["candidate_registry_sha256"]:
        raise ValueError("initial input registry hash does not match sealed source report")
    if Counter(x["split"] for x in old) != {"development": 25, "validation": 50, "locked_test": 125}:
        raise ValueError("unexpected historical split counts")
    return old, screening, sha(raw), sha(prior_report_raw)


def stable_rank(row):
    token = f"{SEED}|{row['category']}|{row['query_id']}|{row['preference_sha256']}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest(), row["query_id"]


def build():
    old, source, old_sha, old_report_sha = input_registry()
    groups = defaultdict(list)
    for row in old:
        if row["category"] not in TARGET or row["split"] not in SPLITS:
            raise ValueError("unknown source category/split")
        groups[(row["category"], row["split"])].append(row)
    assignments = {}
    quotas = {}
    for category in CATEGORIES:
        want = TARGET[category]
        old_dev = groups[category, "development"]
        old_val = groups[category, "validation"]
        old_test = groups[category, "locked_test"]
        if len(old_dev) > want["development"] or len(old_val) < want["validation"] or len(old_test) < want["locked_test"]:
            raise ValueError("allocation quotas incompatible with source selection")
        if sum(want.values()) != len(old_dev) + len(old_val) + len(old_test):
            raise ValueError("category count changed")
        # Retain exactly the requested old val/test members, chosen from IDs
        # and normalized preference SHA hashes alone (no model/test outcomes).
        old_val_ranked = sorted(old_val, key=stable_rank)
        old_test_ranked = sorted(old_test, key=stable_rank)
        val_kept = old_val_ranked[:want["validation"]]
        test_kept = old_test_ranked[:want["locked_test"]]
        dev_additions = old_val_ranked[want["validation"]:] + old_test_ranked[want["locked_test"]:]
        if len(old_dev) + len(dev_additions) != want["development"]:
            raise AssertionError("development quota arithmetic")
        for row in old_dev + dev_additions:
            assignments[row["query_id"]] = "development"
        for row in val_kept:
            assignments[row["query_id"]] = "validation"
        for row in test_kept:
            assignments[row["query_id"]] = "locked_test"
        quotas[category] = dict(want)
    if set(assignments) != {row["query_id"] for row in old}:
        raise AssertionError("task dropped from split")
    # Preserve all original row fields and their original order.
    new_rows = [{**r, "split": assignments[r["query_id"]]} for r in old]
    if Counter(r["split"] for r in new_rows) != {
        "development": 80, "validation": 40, "locked_test": 80
    }:
        raise AssertionError("candidate allocation totals")
    seen_dev = {r["query_id"] for r in old if r["split"] == "development"}
    if not seen_dev.issubset({r["query_id"] for r in new_rows if r["split"] == "development"}):
        raise AssertionError("previously inspected development task escaped into heldout")
    transitions = {src: dict(sorted(Counter(
        assignments[r["query_id"]] for r in old if r["split"] == src
    ).items())) for src in SPLITS}
    if transitions != {
        "development": {"development": 25},
        "validation": {"development": 10, "validation": 40},
        "locked_test": {"development": 45, "locked_test": 80}
    }:
        raise AssertionError("unexpected initial->current transitions")
    report = {
        "schema": "costbench-candidate-allocation-80-40-80",
        "status": "candidate_membership_only_not_validated_native_agent_results",
        "reason": "more development capacity for method design; retained independent final evaluation",
        "seed": SEED,
        "selection_inputs": "sealed source query IDs, task category, normalized preference SHA only",
        "upstream_commit": source["upstream_commit"],
        "source_queries_sha256": source["source_sha256"],
        "source_registry_raw_sha256": old_sha,
        "source_screening_report_raw_sha256": old_report_sha,
        "source_registry_canonical_sha256": source["candidate_registry_sha256"],
        "allocated_registry_canonical_sha256": sha(canonical(new_rows).encode("utf-8")),
        "distinct_base_tasks": 200,
        "target_split_counts": {"development": 80, "validation": 40, "locked_test": 80},
        "category_split_quotas": quotas,
        "source_to_allocation_transition_counts": transitions,
        "retained_previously_screened_development_tasks": len(seen_dev),
        "previously_screened_dev_ids_preserved": True,
        "disjoint_query_and_preference_signatures": True,
        "task_source_or_gold_read": False,
        "validation_test_graph_read": False,
        "model_or_native_calls": 0,
        "scientific_limitations": [
            "The previously screened 25 development cases remain in development.",
            "Reassigned tasks are candidates, not completed model or native simulation trials.",
            "The original source-selection manifest and experiment evidence remain unchanged.",
            "Task metadata-based separation does not guarantee semantic independence.",
            "New development graph/event checking must never be treated as confirmation of final test performance."
        ],
    }
    return new_rows, report


def write_or_check(rows, report, check=False):
    out = HERE / "generated"
    registry = out / "candidate_registry.jsonl"
    summary = out / "ALLOCATION_REPORT.json"
    registry_text = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows)
    summary_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if check:
        if registry.read_text(encoding="utf-8") != registry_text or summary.read_text(encoding="utf-8") != summary_text:
            raise AssertionError("candidate allocation differs from the frozen source")
    else:
        out.mkdir(parents=True, exist_ok=True)
        registry.write_text(registry_text, encoding="utf-8")
        summary.write_text(summary_text, encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    rows, report = build()
    write_or_check(rows, report, args.check)
    print("CANDIDATE_ALLOCATION " + json.dumps({
        "counts": report["target_split_counts"],
        "transitions": report["source_to_allocation_transition_counts"],
        "unchanged_screened_dev": report["retained_previously_screened_development_tasks"],
        "no_model_calls": True,
    }, sort_keys=True))
