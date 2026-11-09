# Reproducibility

This guide uses the **unified 50-task paired benchmark** as the canonical RETAIN/SWITCH study. The 45 preserved source task pairs are merged into one file at `experiments/paired_50/provenance/source_records/source_archive/source_pairs.json`; users do not need to run historical source-generation workflows to access or score the current dataset.

## Quick start: offline verification

Use Python 3.12 from the repository root:

```bash
python scripts/build_release_manifest.py --check
python scripts/check_release.py
python scripts/check_markdown_links.py
python experiments/paired_50/build_unified_dataset.py --check
python -m unittest discover -s scripts -v
python -m unittest discover -s experiments/paired_50/native_execution -p 'test_*.py' -v
```

The dataset builder's `--check` mode rebuilds the canonical registry, manifest, requests and pair fixture in memory, then compares them with the committed frozen outputs. It makes no model API calls. The unit tests verify task counts, category balance, matched checkpoints, frozen request hashes, saved structured scores and source-fixture disjointness.

## Canonical paired dataset

The canonical files are under `experiments/paired_50/generated/`:

- `task_registry_50.json` — 50 independent task IDs and category metadata.
- `pairs_50.json` — 50 matched task fixtures.
- `trial_manifest_100.json` — 100 condition records with checkpoint and request hashes.
- `model_requests_100.jsonl` — 100 frozen model-visible requests.
- `BUILD_REPORT.json` — deterministic dataset build accounting.

The canonical builder combines the single merged source archive with five newly generated task fixtures at `experiments/paired_50/generated/pairs.json`. The original raw source materials and earlier evaluation records remain nested under `source_archive/` for provenance.

Pinned upstream CostBench revision: `6424069f3f773ade076bcedbed302ed47cfb1837`.

To regenerate the five extension fixtures, use a pinned CostBench checkout:

```bash
python experiments/paired_50/generate_extension.py --costbench-root ../CostBench
python experiments/paired_50/build_unified_dataset.py
python experiments/paired_50/build_unified_dataset.py --check
```

Do not overwrite the frozen dataset when only verifying a release. Regeneration is a deliberate operation and should be performed on a working branch.

## Structured model evaluation

Saved DeepSeek Flash responses, the ledger and scores are under `experiments/paired_50/live_results/deepseek-flash/`. Offline integrity tests compare the committed score totals and frozen request hashes.

The runner `experiments/paired_50/run_deepseek.py` is dry-run by default. Paid calls require an explicit live flag and a configured provider key. Re-running the model evaluation is not necessary for reproducing the saved score file.

## Native CostBench execution

The 100 native trajectories, scoring and execution accounting are documented in [native execution protocol](../experiments/paired_50/native_execution/README.md) and [native results](../experiments/paired_50/native_execution/RESULTS.md). The offline workflow reconstructs the frozen checkpoints and validates the protocol using the pinned upstream harness. Repeating live native execution requires provider access and incurs charges.

## Separate evidence packages

- [Official 80-task native dynamic-robustness audit](../experiments/native_80/README.md) — static/dynamic final-answer comparison.
- [Plan-commitment and evidence-gate audit](../research/costbench_method_studies/plan_commitment_evidence_gate/README.md) — 67 event checkpoints, 27 authentic prospective plans.
- [Mechanism diagnosis](../experiments/mechanism_diagnosis/README.md) and [intervention feasibility](../experiments/interventions/README.md) — development-task diagnostics and prototypes.

These are separate studies with separate denominators. Do not add their sample counts to the 50-task paired benchmark.
