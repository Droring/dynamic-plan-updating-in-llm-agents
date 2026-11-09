# Experimental Design

The [study protocol](STUDY_PROTOCOL.md) is the canonical operational definition. This page summarizes the current design and links to its frozen evidence.

## Primary paired benchmark

The [Unified RETAIN/SWITCH Decision and Native Execution Study](../experiments/paired_50/README.md) contains 50 independent CostBench base tasks. Each task has two matched conditions from the same checkpoint: RETAIN and SWITCH. The dataset has 100 condition records and ten tasks in each of five CostBench categories.

Two evaluation protocols use the same base-task set:
- Structured decision: explicit RETAIN/SWITCH label.
- Native execution: first executed tool compared with the incumbent suffix's first tool.

Their scores are reported separately because they measure different outcomes.

## Complementary evidence

- The official native dynamic-robustness audit contains 80 tasks and compares static/dynamic final-answer outcomes; one task is shared with the 50-task paired cohort.
- The plan-commitment/evidence-gate audit contains 67 replay-matched event checkpoints from 80 candidates.
- Mechanism diagnosis and intervention feasibility studies reuse development tasks and are reported as exploratory evidence.

These evidence packages have distinct denominators and must not be added to the 50-task paired benchmark.

## Where to find the evidence

- [Unified benchmark](../experiments/paired_50/README.md) — canonical registry, frozen requests, structured scores and native execution.
- [Experiment index](../experiments/README.md) — all current evidence packages.
- [Results summary](RESULTS_SUMMARY.md) — current headline results.
- [Claim-evidence matrix](CLAIM_EVIDENCE_MATRIX.md) — claim-level source mapping.
- [Reproducibility](REPRODUCIBILITY.md) — offline checks and external dependencies.
- [Limitations](LIMITATIONS.md) — interpretation boundaries.
