# Native 100-Trajectory Path-Value Audit

## Protocol and validation

This is an offline audit of the frozen 50-task paired cohort (100 native tool-execution trajectories). It makes no model/API calls. Each executed tool sequence is replayed against the frozen request's current tool schemas, type preconditions, output types and values. Every trace tool call must be successful, its recorded `tool_cost` must match the frozen current tool value, and the path must reach the goal.

An independent Dijkstra implementation over the same monotone type-state graph is run for every trajectory. Its optimal value is checked against the value of the `native_optimal_path_audit` saved by the pinned CostBench solver. **100/100** native solver path values matched the independent computation within numerical tolerance. All 100 actual traces were feasible and successful. The Bellman per-action decomposition reconciles with full-path regret for all 100 trajectories.

## Main path-value results

| Measure | RETAIN condition | SWITCH condition | Overall |
|---|---:|---:|---:|
| Value-optimal executed paths | 48/50 (96%) | 2/50 (4%) | 50/100 (50%) |
| Mean executed path value | 69.74 | 70.42 | 70.08 |
| Mean native optimum | 69.73 | 69.17 | 69.45 |
| Total path regret | 0.37 | 62.40 | 62.77 |
| Mean path regret | 0.007 | 1.248 | 0.628 |

The central result is that **48/50 SWITCH-condition trajectories (96%) are value-suboptimal**. In all 48 cases, the Agent executes the exact incumbent suffix, incurring 1.30 regret per trajectory. Only **2/50 SWITCH conditions** reach the current-condition optimum. In the RETAIN condition, 48/50 paths are value-optimal; the two deviations incur smaller regrets of 0.11 and 0.26.

Only **1/50 matched task pairs** is value-optimal in both conditions. The 100% goal-completion rate does not capture this difference.

## First action versus subsequent actions

For each executed action, regret is calculated as:

\[
r_t = c(a_t) + V^*(s_{t+1}) - V^*(s_t),
\]

where (V^*(s)) is the minimum remaining native tool value from state (s) to the goal in the current condition. The sum of per-action regret equals full-path regret.

| Regret component | Total | Share of all path regret |
|---|---:|---:|
| First executed action | 52.53 | 83.7% |
| Subsequent actions | 10.24 | 16.3% |
| Total | 62.77 | 100.0% |

Positive first-action regret occurs in 45/100 trajectories; positive subsequent-action regret occurs in 8/100. Three trajectories have both. Thus, the dominant loss is introduced at the first executed action, while later actions contribute a smaller but non-zero share.

## Interpretation

The dominant failure is not failure to reach the goal. It is failure to change the executed continuation when the updated tool graph makes the incumbent less valuable. In the SWITCH condition, the Agent follows the exact incumbent suffix in 48/50 cases. This is direct evidence of incumbent-plan persistence in the tested checkpoint protocol.

The result does not establish the internal cognitive cause or validate an intervention. The next mechanism study should distinguish (1) direct copying/anchoring on the supplied incumbent, (2) failure to recompute the remaining plan after observing the updated tool environment, and (3) later execution drift after an initially appropriate first action.

## Mechanism-relevant prompt audit

The pinned upstream system instruction is not silent about optimization: it explicitly asks the Agent to select the lowest-total-value path, compare candidate paths, and adapt when tool cost or availability changes. The checkpoint message also says the environment has changed and permits either continuing the incumbent or choosing another feasible continuation.

However, the checkpoint message does not identify the changed tool, show its previous and current values, or provide a structured before/after delta. The model receives 14 current tool interfaces per task; each interface description contains that tool's current value. The incumbent suffix is explicitly supplied, while the previous tool-value snapshot is not.

A post-hoc split by the location of the changed tool reveals a useful asymmetry:

| SWITCH fixture type | Tasks | First action still followed incumbent | Value-optimal paths |
|---|---:|---:|---:|
| Changed tool is part of incumbent; its value increases | 26 | 24/26 | 2/26 |
| Changed tool is outside incumbent; an alternative becomes cheaper | 24 | 24/24 | 0/24 |

Both successful SWITCH trajectories occur when the incumbent tool itself becomes more expensive (Query00440 and Query00662). The Agent never switches in the 24 cases where the improvement is confined to a non-incumbent alternative.

This suggests two separable candidate mechanisms: weak detection of degradation to a tool already in the incumbent, and an even stronger failure to discover newly improved alternatives. The pattern is consistent with incumbent anchoring and limited counterfactual search, but the observational split does not establish causality. A controlled prompt probe should separately manipulate explicit change localization and incumbent-plan salience while keeping the current tool graph, checkpoint, objective instruction, and execution budget fixed.

## Reproduction

The audit script uses only the frozen requests and archived response records. It does not import or call the model provider.

```bash
python native_path_value_audit.py \
  --responses PATH_TO_ARCHIVED_RESPONSES_JSONL \
  --requests ../generated/model_requests_100.jsonl \
  --out-dir path_value_audit
```

Outputs:
- `summary.json` — aggregate path-value and decomposition results;
- `trajectory_value_audit.csv` — one row per trajectory;
- `action_regret_decomposition.csv` — one row per executed tool action.

The raw response archive is retained separately and identified by its SHA-256 in [RESULTS.md](RESULTS.md).
