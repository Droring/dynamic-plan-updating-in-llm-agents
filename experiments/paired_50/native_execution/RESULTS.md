# Paired 50 native CostBench execution — DeepSeek Flash

**Status:** Complete  
**Scored cohort:** 100 trajectories across 50 paired base tasks  
**Provider-reported model:** `deepseek-flash`  
**Pinned CostBench revision:** `6424069f3f773ade076bcedbed302ed47cfb1837`

## Main results

The archived cohort contains 100 completed trajectories across 50 paired base tasks. All 100 trajectories reached the goal and the first native tool action succeeded in all 100.

The first-action label is a descriptive comparison with the incumbent: `RETAIN` means the first executed tool equals the incumbent suffix's first tool; `SWITCH` means it differs. It does **not** establish whether the resulting continuation is optimal under the changed environment. The archived trace does not, by itself, provide a validated path-level optimality score.

| Descriptive measure | Result |
|---|---:|
| RETAIN-condition trials whose first action followed incumbent | 48/50 (96%) |
| SWITCH-condition trials whose first action followed incumbent | 48/50 (96%) |
| Total first actions following incumbent | 96/100 (96%) |
| Total first actions departing from incumbent | 4/100 (4%) |
| Goal state reached | 100/100 |
| First native tool action succeeded | 100/100 |
| Exact incumbent suffix executed | 96/100 |
| Alternative continuation observed | 4/100 |

The key observed behavior is that the model followed the incumbent first action in 48/50 SWITCH conditions. This is evidence of strong incumbent persistence in this protocol. The four deviations are not counted as successful switches without a separate comparison against the current-condition optimum.

## Paired first-action behavior

Each cell reports the first-action relation to the incumbent in the RETAIN and SWITCH conditions, respectively.

| Paired behavior (RETAIN / SWITCH) | Number of base tasks |
|---|---:|
| RETAIN / RETAIN | 47 |
| RETAIN / SWITCH | 1 |
| SWITCH / RETAIN | 1 |
| SWITCH / SWITCH | 1 |

Only one pair showed the expected first-action distinction (RETAIN under RETAIN, SWITCH under SWITCH). This is a behavioral pairing result, not a path-optimality score.

## Interpretation boundary

The native solver computes an optimal continuation in the current tool-cost graph, while the model executes tool calls from the same visible registry. However, the archived execution summary does not include a verified end-to-end comparison of each executed continuation's cumulative cost against the solver's optimal total cost. A raw tool-sequence equality check is not a valid substitute unless action granularity and composite-tool representation are shown to be equivalent.

Accordingly, this report describes incumbent adherence, observed deviations, and goal completion. It does not claim that all four deviations are correct switches or that the two-condition path-optimality rate is 2%.

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
