#!/usr/bin/env python3
"""Build/check the canonical 50-task / 100-condition CostBench paired dataset offline."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "experiments" / "paired_50" / "provenance" / "source_records"
OUT = ROOT / "experiments" / "paired_50" / "generated"

def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    return value["pairs"] if isinstance(value, dict) and "pairs" in value else value

def sha(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="rebuild in memory and verify frozen outputs")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("extension", ROOT / "experiments" / "paired_50" / "generate_extension.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    groups = [
        ("source_archive", read_json(SOURCES / "source_archive" / "source_pairs.json")),
        ("new_extension", read_json(OUT / "pairs.json")),
    ]
    pairs, source = [], {}
    for source_name, rows in groups:
        for pair in rows:
            qid = pair["query_id"]
            if qid in source:
                raise ValueError("duplicate task ID: " + qid)
            source[qid] = source_name
            pairs.append(pair)
    if len(pairs) != 50:
        raise ValueError(f"expected 50 tasks, got {len(pairs)}")
    categories = Counter(pair["task"] for pair in pairs)
    expected = {category: 10 for category in module.CATEGORIES}
    if dict(categories) != expected:
        raise ValueError(f"category balance mismatch: {dict(categories)}")
    if len({pair["checkpoint_sha256"] for pair in pairs}) != 50:
        raise ValueError("checkpoint hashes must be task-unique")

    task_records = []
    pair_by_id = {pair["query_id"]: pair for pair in pairs}
    for index, pair in enumerate(pairs, 1):
        if [row["name"] for row in pair["conditions"]] != ["RETAIN", "SWITCH"]:
            raise ValueError("condition order mismatch: " + pair["query_id"])
        task_records.append({
            "task_id": pair["query_id"], "task_index": index, "category": pair["task"],
            "source_record": source[pair["query_id"]], "checkpoint_sha256": pair["checkpoint_sha256"]
        })

    rng = random.Random(module.SELECTION_SEED)
    switch_first = set(rng.sample(range(50), 25))
    requests, manifest = [], []
    for index, pair in enumerate(pairs):
        labels = ["SWITCH", "RETAIN"] if index in switch_first else ["RETAIN", "SWITCH"]
        for label in labels:
            request = module.create_request(pair, label)
            requests.append(request)
            manifest.append({
                "trial_id": request["trial_id"], "query_id": request["query_id"], "condition": label,
                "request_sha256": sha(request), "checkpoint_sha256": request["checkpoint_sha256"]
            })

    if len(requests) != 100 or len({row["trial_id"] for row in requests}) != 100:
        raise ValueError("expected 100 unique model requests")
    if Counter(row["condition"] for row in manifest) != {"RETAIN": 50, "SWITCH": 50}:
        raise ValueError("condition balance mismatch")
    for qid in pair_by_id:
        rows = [row for row in manifest if row["query_id"] == qid]
        if len(rows) != 2 or {row["condition"] for row in rows} != {"RETAIN", "SWITCH"}:
            raise ValueError("unpaired requests: " + qid)
        if len({row["checkpoint_sha256"] for row in rows}) != 1:
            raise ValueError("checkpoint mismatch: " + qid)

    registry = {
        "dataset_id": "costbench_paired_retain_switch_50",
        "title": "Unified 50-task CostBench RETAIN/SWITCH paired dataset",
        "upstream_revision": module.UPSTREAM_SHA,
        "base_task_count": 50, "condition_count": 100, "unique_task_ids": 50,
        "condition_balance": {"RETAIN": 50, "SWITCH": 50},
        "categories": dict(categories),
        "selection": {"task_ids": task_records, "disjoint_extension_verified": True,
                      "each_task_has_one_retain_and_one_switch": True},
        "model_protocol": {"model": "deepseek-flash", "temperature": 0, "thinking": "disabled",
                           "prompt_template": "experiments/paired_50/generate_extension.py::SYSTEM",
                           "protocol_version": "unified-50-v1"}
    }
    trial_manifest = {"dataset_id": registry["dataset_id"], "trial_count": 100, "records": manifest}
    public_pairs = {"format": "unified_costbench_paired_50_v1", "upstream_sha": module.UPSTREAM_SHA, "pairs": pairs}
    report = {
        "status": "offline_dataset_built_no_model_calls", "base_tasks": 50, "conditions": 100,
        "category_counts": dict(categories), "condition_counts": {"RETAIN": 50, "SWITCH": 50},
        "source_counts": dict(Counter(source.values())), "task_ids": [pair["query_id"] for pair in pairs],
        "request_count": 100, "unique_request_ids": 100, "model_calls": 0, "budget_charged": 0
    }
    outputs = {
        "task_registry_50.json": json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        "trial_manifest_100.json": json.dumps(trial_manifest, ensure_ascii=False, indent=2) + "\n",
        "model_requests_100.jsonl": "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in requests),
        "pairs_50.json": json.dumps(public_pairs, ensure_ascii=False, indent=2) + "\n",
        "BUILD_REPORT.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit("stale or missing generated file: " + name)
        else:
            path.write_text(content, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
