#!/usr/bin/env python3
"""Assert the canonical 50-task dataset and descriptive CostBench registry paths exist."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "experiments/paired_50/README.md",
    "experiments/paired_50/build_unified_dataset.py",
    "experiments/paired_50/generated/task_registry_50.json",
    "experiments/paired_50/generated/trial_manifest_100.json",
    "experiments/paired_50/live_results/deepseek-flash/scores.json",
    "experiments/paired_50/native_execution/README.md",
    "experiments/paired_50/provenance/source_records/source_archive/source_pairs.json",
    "experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated/pairs.json",
    "experiments/paired_50/provenance/source_records/source_archive/raw_source_material_b/generated/pairs.json",
    "experiments/paired_50/provenance/source_records/source_archive/historical_evaluation_records/live_results/scores.json",
    "research/costbench_method_studies/candidate_source_registry/generated/candidate_registry.jsonl",
    "research/costbench_method_studies/official_native_task_allocation/generated/candidate_registry.jsonl",
)
RETIRED = (
    "experiments/paired_45",
    "experiments/paired_45/initial_30_task_cohort",
    "experiments/paired_45/additional_15_task_cohort",
    "experiments/paired_45/additional_15_task_evaluation",
    ".github/workflows/additional-15-task-cohort.yml",
    ".github/workflows/paired-cohort-evaluation.yml",
    ".github/workflows/plan-commitment-historical45-verify.yml",
    "scripts/test_paired_45_unified_dataset.py",
)
missing = [name for name in REQUIRED if not (ROOT / name).exists()]
stale = [name for name in RETIRED if (ROOT / name).exists()]
if missing or stale:
    print("Missing canonical artifacts:", missing)
    print("Retired paths still present:", stale)
    raise SystemExit(1)
print("Canonical unified 50-task layout verified.")
print(f"Required artifacts: {len(REQUIRED)}; retired paths absent: {len(RETIRED)}.")
