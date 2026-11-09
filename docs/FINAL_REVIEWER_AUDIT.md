# Reviewer-Facing Audit — Unified 50-Task Study

## Main empirical package

The canonical paired benchmark contains 50 independent CostBench base tasks and 100 matched conditions. Each task has one RETAIN and one SWITCH condition from a shared frozen checkpoint.

| Outcome | Structured decision | Native first action |
|---|---:|---:|
| RETAIN accuracy | 48/50 | 48/50 |
| SWITCH accuracy | 3/50 | 2/50 |
| Paired accuracy | 1/50 | 1/50 |
| Goal reached | — | 100/100 |

The structured protocol and native execution protocol are distinct and must not be pooled. In native execution, the first-action decision was the same across matched conditions in 48/50 pairs.

## Strengths

- Explicit independent-task denominator and matched condition design.
- Same checkpoint for both conditions of each base task.
- Frozen requests, manifests and request hashes.
- Category-balanced task selection.
- Separate structured-decision and native-execution measurements.
- Reproducible offline dataset builder and validation workflow.
- Preserved source records for audit without requiring readers to navigate historical cohorts.

## Main limitations

- The incumbent suffix is solver-derived and supplied at the checkpoint; this is not a self-authored plan-commitment experiment.
- The RETAIN/SWITCH objective is defined on a controlled CostBench tool graph.
- Goal completion can conceal an incorrect first action.
- The official 80-task dynamic-robustness audit and 67-checkpoint plan-commitment audit are separate studies.
- EDR and Action Guard have not demonstrated an end-to-end advantage over simple explicit fact updating.

## Claims suitable for the current artifact

The current results support reporting a strong RETAIN/SWITCH asymmetry in the tested paired protocol and weak first-action adaptation in native execution. They do not support claiming a validated new algorithm, a causal self-commitment effect, or that all dynamic failures share one mechanism.

See [claim-evidence matrix](CLAIM_EVIDENCE_MATRIX.md), [limitations](LIMITATIONS.md), [reproducibility](REPRODUCIBILITY.md), and the [canonical study](../experiments/paired_50/README.md).
