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

## Path-value audit

The subsequent offline audit replays all 100 executed paths against the frozen current tool graph and compares their total value with the current-condition native optimum. An independent Dijkstra implementation matches the pinned solver's saved optimal-path value in **100/100** trials.

- RETAIN: 48/50 executed paths are value-optimal; the other two have regret 0.11 and 0.26.
- SWITCH: only 2/50 executed paths are value-optimal. The other 48 execute the exact incumbent suffix and each has regret 1.30.
- Paired value-optimality: 1/50 task pairs are optimal in both conditions.
- Total path regret: 62.77; 52.53 (83.7%) is introduced by the first action and 10.24 (16.3%) by subsequent actions.

See [NATIVE_PATH_VALUE_AUDIT.md](NATIVE_PATH_VALUE_AUDIT.md) for the complete method, validation and interpretation, and [trajectory-level CSV](path_value_audit/trajectory_value_audit.csv) when generated from the archived artifact.

