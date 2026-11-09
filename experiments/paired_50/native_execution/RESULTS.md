# Paired 50 native CostBench execution — DeepSeek Flash

**Status:** Complete  
**Scored cohort:** 100 trajectories across 50 paired base tasks  
**Provider-reported model:** `deepseek-flash`  
**Pinned CostBench revision:** `6424069f3f773ade076bcedbed302ed47cfb1837`

## Main results

The archived cohort contains 100 completed trajectories across 50 paired base tasks. All 100 trajectories reached the goal and the first native tool action succeeded in all 100.

The first-action label is a descriptive comparison with the incumbent: `RETAIN` means the first executed tool equals the incumbent suffix's first tool; `SWITCH` means it differs. Path-level optimality is evaluated separately in the offline value audit.

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

## Path-value audit

The subsequent offline audit replays all 100 executed paths against the frozen current tool graph and compares their total value with the current-condition native optimum. An independent Dijkstra implementation matches the pinned solver's saved optimal-path value in **100/100** trials.

- RETAIN: 48/50 executed paths are value-optimal; the other two have regret 0.11 and 0.26.
- SWITCH: only 2/50 executed paths are value-optimal. The other 48 execute the exact incumbent suffix and each has regret 1.30.
- Paired value-optimality: 1/50 task pairs are optimal in both conditions.
- Total path regret: 62.77; 52.53 (83.7%) is introduced by the first action and 10.24 (16.3%) by subsequent actions.

See [NATIVE_PATH_VALUE_AUDIT.md](NATIVE_PATH_VALUE_AUDIT.md) for the complete method, validation and interpretation. The [mechanism analysis](MECHANISM_ANALYSIS.md) stratifies SWITCH failures by the location and direction of the changed tool value and reports paired first-action consistency.

## Execution record

The initial run completed 66 trajectories. Its 67th trajectory executed one successful native tool call and stopped at the token reservation guard. The continuation restarted that same frozen trial from its original checkpoint, completed it, and then completed the remaining 33 trials. The scored cohort comprises 66 completed initial records plus 34 completed continuation records; the superseded partial attempt is excluded from scoring and included in accounting.

- Scored provider usage: **1,191,160 tokens** across 287 model calls.
- Superseded partial attempt: **5,688 tokens** across one model call.
- Total provider usage across both runs: **1,196,848 tokens**.
- API errors: 0; runner errors: 0; incomplete scored trajectories: 0.

## Reproducibility

The frozen request SHA-256 is `a3f368ee12b7edc6fdea1fa6da90779a93c3e8c5b1d57309876784268d56c9e7`. The frozen manifest SHA-256 is `ef1470f06191ce2d8792da8034dc6e1225d6ddda4f6bb5c29cae6a642579a8c8`.

The merged historical archive was recovered from the retired repository's Actions storage and inspected offline. Its raw per-trajectory files are not yet committed in this repository. The recovered ZIP is identified by artifact ID `13646976640` and SHA-256 `6587a6b2c319069d27d07fe9ca21eb3464b38f200f73f6ef4555208b13694630`.
