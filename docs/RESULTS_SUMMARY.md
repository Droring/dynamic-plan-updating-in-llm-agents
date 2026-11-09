# Results Summary

This page summarizes the current canonical findings. See the individual evidence packages for protocols and raw results.

## Unified 50-task paired study

| Measure | Structured decision labels | Native first-action behavior | Native path-value audit |
|---|---:|---:|---:|
| Independent base tasks | 50 | 50 | 50 |
| Matched conditions / trajectories | 100 | 100 | 100 |
| RETAIN condition | 48/50 correct (96%) | 48/50 followed incumbent (96%) | 48/50 value-optimal (96%) |
| SWITCH condition | 3/50 correct (6%) | 48/50 followed incumbent (96%) | 2/50 value-optimal (4%) |
| Paired outcome | 1/50 correct (2%) | 1/50 expected first-action distinction | 1/50 optimal in both conditions |
| Goal reached | — | 100/100 | 100/100 |

The structured protocol evaluates an explicit decision label. Native first-action adherence and path-value optimality are separate execution measures; they must not be conflated. The path-value audit validates the executed continuation against the current-condition native optimum.

The path-value audit independently recomputes shortest-path values for all 100 conditions and matches the pinned native solver's saved optimal-path values in 100/100 cases. Of 62.77 total regret units, 52.53 (83.7%) arise at the first executed action and 10.24 (16.3%) during subsequent actions. The Agent follows the exact incumbent suffix in 48/50 SWITCH conditions. See the [native path-value audit](../experiments/paired_50/native_execution/NATIVE_PATH_VALUE_AUDIT.md).

## Official native dynamic robustness

The separate official CostBench audit contains 80 tasks: 70/80 static final answers and 60/80 dynamic final answers were accepted. Thirteen tasks changed from static-correct to dynamic-incorrect; three changed in the opposite direction.

## Additional evidence

The plan-commitment/evidence-gate audit contains 67 replay-matched event checkpoints and 27 authentic prospective plans. EDR and Action Guard did not demonstrate an end-to-end advantage over a simple explicit fact-update baseline in the four-task development pilot.

## Interpretation

The primary paired study shows a strong RETAIN/SWITCH response asymmetry under its controlled checkpoint protocol. The native 80-task audit separately shows lower final-answer acceptance under dynamic execution. The current evidence does not establish that every dynamic failure is caused by plan commitment, nor does it validate a new algorithm.

Start with the [unified 50-task study](../experiments/paired_50/README.md), [research mainline](../research/plan_commitment_pilot/RESEARCH_MAINLINE.md) and [limitations](LIMITATIONS.md).
