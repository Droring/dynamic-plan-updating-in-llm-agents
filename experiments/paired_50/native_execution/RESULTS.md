# Paired 50 native CostBench execution — DeepSeek Flash

**Status:** Complete  
**Scored cohort:** 100 trajectories across 50 paired base tasks  
**Provider-reported model:** `deepseek-flash`  
**Pinned CostBench revision:** `6424069f3f773ade076bcedbed302ed47cfb1837`

## Main results

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | 48/50 (96%) |
| SWITCH first-action accuracy | 2/50 (4%) |
| Overall first-action accuracy | 50% |
| Model predicted RETAIN | 96/100 (96%) |
| Model predicted SWITCH | 4/100 (4%) |
| Always-RETAIN baseline accuracy | 50% |
| Balanced accuracy | 50% |
| Paired RETAIN/SWITCH accuracy | 1/50 (2%) |
| Same decision in both paired conditions | 48/50 (96%) |
| Goal state reached | 100/100 |
| First native tool action succeeded | 100/100 |
| Exact incumbent suffix executed | 96/100 |
| Alternative continuation executed | 4/100 |

The model selected the incumbent first action in **48/50 SWITCH conditions (96%)**. Across all 100 trajectories, it predicted RETAIN 96 times and SWITCH four times. Its 50% overall accuracy exactly matches an always-RETAIN baseline on this balanced dataset; the class-conditional results expose the asymmetry (96% RETAIN accuracy versus 4% SWITCH accuracy). The first-action prediction was identical across the two conditions in 48/50 pairs (96%); only one pair received the correct RETAIN/SWITCH distinction on both sides.

The model reached the goal in all 100 scored trajectories. Task completion therefore does not capture the central failure: the first action rarely responds to the paired environment condition.

## Paired outcomes

The tuple is (prediction under RETAIN condition, prediction under SWITCH condition).

| Paired outcome | Number of base tasks |
|---|---:|
| RETAIN / RETAIN | 47 |
| RETAIN / SWITCH | 1 |
| SWITCH / RETAIN | 1 |
| SWITCH / SWITCH | 1 |

## The four alternative continuations

| Query | RETAIN-condition first tool | SWITCH-condition first tool | Paired prediction |
|---|---|---|---|
| Query00440 | `Accommodation_Finish_from_Step1_3Steps` | `Accommodation_Refinement_Step1` | RETAIN / SWITCH |
| Query00662 | `Attraction_Refinement_Step1` | `Attraction_Refinement_Step1` | SWITCH / SWITCH |
| Query00598 | `Attraction_Refine_to_Step2` | `Attraction_Finish_from_Step1_3Steps` | SWITCH / RETAIN |

Query00440 is the only pair with the correct distinction. Query00662 switches under both conditions; Query00598 reverses the expected decisions.

## Execution record

The initial full-cohort run completed 66 trajectories. Its 67th trajectory executed one successful native tool call and then stopped at the token reservation guard. The continuation restarted that same frozen trial from its original checkpoint, completed it, and then completed the remaining 33 trials.

The scored cohort consists of the first run's 66 completed records plus all 34 continuation records. The partial first attempt is excluded from the scored cohort and included in execution accounting.

- Scored provider usage: **1,191,160 tokens** across 287 model calls.
- Superseded partial attempt: **5,688 tokens** across one model call.
- Total provider usage across both runs: **1,196,848 tokens**.
- API errors: 0.
- Runner errors: 0.
- Incomplete trajectories in the scored cohort: 0.

## Reproducibility

Historical GitHub Actions artifacts were produced under the retired repository, so their links are intentionally omitted here. The raw per-trajectory `scores.json`, `ledger.json`, and `responses.jsonl` are not included in this repository; this document is a result summary rather than a self-contained raw-data release.


Frozen request SHA-256: `a3f368ee12b7edc6fdea1fa6da90779a93c3e8c5b1d57309876784268d56c9e7`.  
Frozen manifest SHA-256: `ef1470f06191ce2d8792da8034dc6e1225d6ddda4f6bb5c29cae6a642579a8c8`.

The RETAIN/SWITCH label compares the first executed native tool with the incumbent suffix's first tool. Full trajectory relation and goal completion are reported separately. This measures observable execution, not hidden model reasoning.
