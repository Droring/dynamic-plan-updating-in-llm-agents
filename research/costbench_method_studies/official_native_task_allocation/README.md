# Official Native CostBench Task Allocation

This directory records the current allocation of the same 200 CostBench candidate IDs: 80 development, 40 validation and 80 locked-test candidates.

This is a run-organization allocation record, not 200 completed Agent evaluations or a model-training dataset. The official native dynamic-robustness study evaluated the 80 development tasks only. The 40 validation and 80 locked-test candidates were not used in that study.

## Allocation

| Partition | Transportation | Accommodation | Attraction | Dining | Shopping | Total |
|---|---:|---:|---:|---:|---:|---:|
| Development | 24 | 11 | 12 | 15 | 18 | **80** |
| Validation | 12 | 5 | 6 | 7 | 10 | **40** |
| Locked test | 24 | 11 | 11 | 15 | 19 | **80** |
| **Total** | **60** | **27** | **29** | **37** | **47** | **200** |

The allocation preserves the original candidate IDs and source hashes recorded in the [candidate source registry](../candidate_source_registry/README.md). It is included to make the 80-task baseline population auditable; it is separate from the primary 50-task paired benchmark.

## Reproduction

The candidate registry and allocation report are frozen under `generated/`. Run `python research/costbench_method_studies/official_native_task_allocation/build_allocation.py --check` to verify the deterministic allocation. Offline tests verify uniqueness, category quotas and partition membership. They do not run the Agent or invoke a model API.

The 80 development tasks used in the official native audit share one base task, `Query00499`, with the canonical 50-task paired benchmark. Two further overlaps (`Query00260` and `Query00865`) occur only in the unused validation/locked-test candidate records. The official audit therefore contributes 79 distinct base tasks beyond the paired cohort, not 80 independent additional tasks. The validation and locked-test candidates were not executed.
