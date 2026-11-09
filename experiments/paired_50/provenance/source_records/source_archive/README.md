# Unified Source Archive

This archive contains the 45 source task pairs incorporated into the canonical 50-task CostBench benchmark.

- `source_pairs.json` is the single merged source-pair input used by the current dataset builder.
- `raw_source_material_a/` and `raw_source_material_b/` preserve the original fixture-generation records and their hashes.
- `historical_evaluation_records/` preserves earlier model responses and diagnostic evaluations for provenance only.

The two raw source-material folders are retained to preserve source lineage. They are not separate current cohorts, experiments, or evaluation protocols. Current results must be read from `experiments/paired_50/generated/` and `experiments/paired_50/live_results/`.
