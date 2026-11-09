# Results Summary

This page summarizes the current canonical findings. See the individual evidence packages for protocols and raw results.

## Unified 50-task paired study

| Measure | Structured decisions | Native first action |
|---|---:|---:|
| Independent base tasks | 50 | 50 |
| Matched conditions / trajectories | 100 | 100 |
| RETAIN accuracy | 48/50 (96%) | 48/50 exact optimal-path match (96%) |
| SWITCH accuracy | 3/50 (6%) | 2/50 exact optimal-path match (4%) |
| Paired accuracy | 1/50 (2%) | 1/50 (2%) |
| Goal reached | — | 100/100 |

The structured protocol evaluates an explicit decision label. The native protocol evaluates the full executed path against the solver's current-condition optimal path; incumbent first-action deviation is descriptive only. These outcomes are not interchangeable.

In native execution, the first-action decision was identical across both matched conditions in 48/50 pairs, despite all 100 trajectories reaching the goal. Goal completion therefore does not establish correct adaptation of the first action.

## Official native dynamic robustness

The separate official CostBench audit contains 80 tasks: 70/80 static final answers and 60/80 dynamic final answers were accepted. Thirteen tasks changed from static-correct to dynamic-incorrect; three changed in the opposite direction.

## Additional evidence

The plan-commitment/evidence-gate audit contains 67 replay-matched event checkpoints and 27 authentic prospective plans. EDR and Action Guard did not demonstrate an end-to-end advantage over a simple explicit fact-update baseline in the four-task development pilot.

## Interpretation

The primary paired study shows a strong RETAIN/SWITCH response asymmetry under its controlled checkpoint protocol. The native 80-task audit separately shows lower final-answer acceptance under dynamic execution. The current evidence does not establish that every dynamic failure is caused by plan commitment, nor does it validate a new algorithm.

Start with the [unified 50-task study](../experiments/paired_50/README.md), [research mainline](../research/plan_commitment_pilot/RESEARCH_MAINLINE.md) and [limitations](LIMITATIONS.md).
