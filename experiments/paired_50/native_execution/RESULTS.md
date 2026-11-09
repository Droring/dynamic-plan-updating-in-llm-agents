# Paired 50 native CostBench execution — DeepSeek Flash

**Status:** Complete  
**Scored cohort:** 100 trajectories across 50 paired base tasks  
**Provider-reported model:** `deepseek-flash`  
**Pinned CostBench revision:** `6424069f3f773ade076bcedbed302ed47cfb1837`

## Main results

The archived per-trajectory artifact was recovered from the retired repository's workflow artifact and independently re-scored against the pinned native solver path stored in each record. The previous first-action-only metric is retained as a descriptive behavior measure, but it is not treated as correctness.

| Measure | Result |
|---|---:|
| RETAIN exact optimal-path match | 48/50 (96%) |
| SWITCH exact optimal-path match | 2/50 (4%) |
| Overall exact optimal-path match | 50/100 (50%) |
| RETAIN first action matched incumbent | 48/50 (96%) |
| SWITCH first action departed from incumbent | 2/50 (4%) |
| Paired exact-path accuracy | 1/50 (2%) |
| Goal state reached | 100/100 |
| First native tool action succeeded | 100/100 |
| Exact incumbent suffix executed | 96/100 |
| Alternative continuation executed | 4/100 |

The key correction is that a first action different from the incumbent is not, by itself, a correct SWITCH. Correctness is now defined by exact equality between the executed continuation and the current-condition optimal path returned by the pinned native CostBench solver. The incumbent relation is reported separately.

Under this path-level criterion, the RETAIN result remains 48/50 and the SWITCH result is 2/50. The model follows the incumbent continuation in 48/50 SWITCH conditions. All 100 trajectories reach the goal, which is a separate outcome and does not establish optimal adaptation.

## Paired outcomes

Each cell reports whether the executed path exactly matched the current-condition optimal path.

| Paired outcome (RETAIN / SWITCH) | Number of base tasks |
|---|---:|
| Correct / Incorrect | 47 |
| Correct / Correct | 1 |
| Incorrect / Correct | 1 |
| Incorrect / Incorrect | 1 |

Only one base task has both conditions exactly matching their respective optimal paths.

## First-action deviations

The four trajectories that departed from the incumbent first action are not automatically counted as successful switches. Only two of those trajectories match the solver's current-condition optimal path; the other two must be assessed using full-path optimality, not incumbent deviation alone. The full trace records and oracle paths are the authoritative evidence.

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

The incumbent first-action relation is descriptive only. Primary correctness compares the full executed path with the current-condition optimal path recorded by the pinned native solver. This is a strict path-level criterion; alternative paths with equal optimal value are not credited unless they match the solver-returned path. The measure captures observable execution, not hidden model reasoning.
