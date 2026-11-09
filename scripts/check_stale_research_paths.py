"""Fail when active source or workflow files reference retired physical experiment paths."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Historical paths are listed only so CI rejects their accidental reintroduction;
# these strings do not point to active experiment implementations.
RETIRED = (
    "experiments/paired_45/",
    "experiments/paired_45",
    "initial_30_task_cohort/",
    "additional_15_task_cohort/",
    "additional_15_task_evaluation/",
    ".github/workflows/additional-15-task-cohort.yml",
    ".github/workflows/paired-cohort-evaluation.yml",
    ".github/workflows/plan-commitment-historical45-verify.yml",
    "scripts/test_paired_45_unified_dataset.py",
    "research/costbench_method_studies/ab_v1",
    "research/costbench_method_studies/checkpoint_v1",
    "research/costbench_method_studies/selective_controller_v1",
    "research/costbench_method_studies/dataset_v1",
    "research/costbench_method_studies/dataset_v2",
    "experiments/m2_prompt_diagnostic",
    "experiments/m4_certified_verification",
    "experiments/executable_alternative_elicitation",
    "experiments/visible_graph_decision_certificates",
    "experiments/small_pilot_extensions",
    "research/costbench_method_studies/incumbent_bounded_search_analysis",
    "research/costbench_method_studies/same_checkpoint_prompt_intervention",
    "research/costbench_method_studies/state_aligned_controller_comparison",
    "research/official_harness_rerun",
    "data_summary/",
    "archive/retired_structured_probe_audit",
    "research.phase2.ab_v1",
    "research.phase2.checkpoint_v1",
    "research.phase2.selective_controller_v1",
    "research.phase2.dataset_v1",
    "research.phase2.dataset_v2",
    "../ab_v1/",
    "../checkpoint_v1/",
    "../selective_controller_v1/",
    "../dataset_v1/",
    "../dataset_v2/",
    "expansion_30",
    "heldout_15",
    "three_pilots_15",
    "experiments/heldout_15/",
    "experiments/three_pilots_15/",
    "scripts/test_heldout_15.py",
    "scripts/test_three_pilots_15.py",
    ".github/workflows/expansion-30-offline.yml",
    ".github/workflows/heldout-15-offline.yml",
    "research/costbench_method_studies/phase2d/",
    "research.phase2.phase2d",
    ".github/workflows/m2-archive-once.yml",
    ".github/workflows/m2-witness-diagnostic.yml",
    ".github/workflows/m4-certified-verification.yml",
    ".github/workflows/m4-economic-controls.yml",
    ".github/workflows/phase2-development-events.yml",
    ".github/workflows/phase2-native-all-development.yml",
    ".github/workflows/phase2-native-gate.yml",
    ".github/workflows/phase2-unified-screening.yml",
    ".github/workflows/phase2-v2-aggregate-once.yml",
    ".github/workflows/phase2-v2-dev55-events-once.yml",
    ".github/workflows/phase2-v2-dev80-events-seal.yml",
    ".github/workflows/phase2-v2-new-dev-once.yml",
    ".github/workflows/phase2-v2-split-once.yml",
    ".github/workflows/three-pilots-15.yml",
    "test_phase2d_bounded.py",
    "native67_v2",
    "native67/",
    "posthoc_probe",
    "verify_posthoc",
)
SUFFIXES = {".py", ".yml", ".yaml"}
tracked = subprocess.run(
    ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
).stdout.split(b"\0")
failures = []
for raw in tracked:
    if not raw:
        continue
    name = raw.decode("utf-8")
    path = ROOT / name
    if (name.startswith("scripts/test_phase2") or name.startswith(".github/workflows/phase2")
            or name in {"scripts/test_heldout_15.py", "scripts/test_three_pilots_15.py"}
            or name in {".github/workflows/expansion-30-offline.yml", ".github/workflows/heldout-15-offline.yml"}):
        failures.append(f"{name}: legacy phase-numbered filename")
        continue
    if path.suffix.lower() not in SUFFIXES or not path.is_file():
        continue
    if name in {"scripts/check_stale_research_paths.py", "scripts/audit_directory_migration.py"} or name.startswith("archive/"):
        continue
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for retired in RETIRED:
        if retired in source:
            for number, line in enumerate(source.splitlines(), 1):
                if retired in line:
                    failures.append(f"{name}:{number}: retired path {retired}")

if failures:
    print("Retired physical experiment paths remain in active code/workflows:")
    print("\n".join(failures))
    raise SystemExit(1)
print("No retired physical experiment paths in tracked Python/YAML source.")
