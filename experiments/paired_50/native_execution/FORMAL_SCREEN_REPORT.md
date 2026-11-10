# Four-Arm Formal Mechanism Screen

## Run provenance

- Repository: `Droring/dynamic-plan-updating-in-llm-agents`
- Branch: `research/four-arm-mechanism-screen`
- Commit: `ae67a858a58e951e9ff9ac6fb49f404ccaf81892`
- GitHub Actions run: [42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176)
- Artifact: `four-arm-deepseek-formal` (artifact ID `13697210404`)
- Artifact SHA-256: `2ae46a0a61cd64db8dea765b79bb8eabef7e3bab9c4872fc4c9ed24d48444cf4`
- Model: `deepseek-flash`; thinking disabled; temperature 0
- Design: 8 reused base tasks x 2 environment conditions x 4 prompt arms x 2 repetitions = 128 requests
- Completed: 128/128; API errors 0; invalid/missing tool calls 0; native tool errors 0
- Accounted tokens: 714,046 / 3,443,584 hard cap (20.7%); no retries
- Raw records: `requests.jsonl`, `responses.jsonl`, `summary.json`, `ledger.json`

## Main result

All 128 first actions were validly executed and scored against the pinned native CostBench minimum-cost continuation.

| Environment | Arm A original | Arm B current-cost reminder | Arm C plan omitted | Arm D plan omitted + reminder |
|---|---:|---:|---:|---:|
| RETAIN optimal first actions | 16/16 (100%) | 16/16 (100%) | 8/16 (50%) | 6/16 (37.5%) |
| SWITCH optimal first actions | 2/16 (12.5%) | 2/16 (12.5%) | 8/16 (50%) | 9/16 (56.25%) |
| RETAIN mean first-action regret | 0.000 | 0.000 | 0.080 | 0.101875 |
| SWITCH mean first-action regret | 1.1375 | 1.1375 | 0.50125 | 0.42375 |
| RETAIN incumbent-first-action matches | 16/16 | 16/16 | 8/16 | 6/16 |
| SWITCH incumbent-first-action matches | 16/16 | 16/16 | 8/16 | 7/16 |

### Task-level paired contrasts

The base task is the independent unit; each task has two repetitions in each environment condition.

| Contrast | SWITCH tasks improved | unchanged | worsened | Mean task-level accuracy difference |
|---|---:|---:|---:|---:|
| B - A (localized current-cost reminder, plan shown) | 0/8 | 8/8 | 0/8 | 0 pp |
| C - A (plan omitted, original update wording) | 3/8 | 5/8 | 0/8 | +37.5 pp |
| D - B (plan omitted under reminder wording) | 4/8 | 4/8 | 0/8 | +43.75 pp |

| Contrast | RETAIN tasks improved | unchanged | worsened | Mean task-level accuracy difference |
|---|---:|---:|---:|---:|
| B - A | 0/8 | 8/8 | 0/8 | 0 pp |
| C - A | 0/8 | 4/8 | 4/8 | -50 pp |
| D - B | 0/8 | 3/8 | 5/8 | -62.5 pp |

The A and B first actions were identical in all 32 matched task x environment x repetition comparisons. This is consistent with the fact that the full current tool descriptions, including current costs for all tools, were already present in every arm. B/D only repeat the changed tool's current cost in the user message; they do not provide new information. The reminder had no observed effect in this cohort.

Plan omission changed the behavior materially:
- In SWITCH, C improved three tasks and harmed none relative to A; D improved four tasks and harmed none relative to B.
- In RETAIN, C worsened four tasks and D worsened five tasks; neither improved any task.
- D attained the best aggregate SWITCH result (9/16), but its RETAIN accuracy fell to 6/16.

This is a pronounced plan-cue trade-off, not an unqualified improvement.

## Task-level pattern

- Query00188 and Query00347: all four arms retained the incumbent first action in SWITCH and incurred regret 1.30; all arms were optimal in RETAIN.
- Query00403: the incumbent first action remained optimal in both environments. It is a necessary counterexample to treating every SWITCH-labelled task as a first-action error.
- Query00518: D corrected both SWITCH repetitions but caused both RETAIN repetitions to become suboptimal.
- Query00550: C corrected both SWITCH repetitions; D did not. Plan omission also harmed RETAIN.
- Query00685: C and D corrected both SWITCH repetitions; both harmed RETAIN.
- Query00706: C did not correct SWITCH; D corrected one of two repetitions. Both C and D harmed RETAIN.
- Query00858: C and D corrected both SWITCH repetitions; both harmed RETAIN.

## Interpretation

### Supported by this experiment

1. Displaying the solver-supplied incumbent plan is associated with highly reliable optimal first actions in RETAIN, but poor switching behavior in most SWITCH checkpoints.
2. Omitting the plan cue increases SWITCH first-action optimality on several tasks, showing that the plan cue itself contributes to the observed behavior in this controlled prompt manipulation.
3. The same plan omission degrades RETAIN decisions on several tasks. Therefore, indiscriminate plan removal is not a suitable solution.
4. Repeating the changed tool's current cost did not improve the first action. Since all current tool costs were already visible in tool descriptions, this is a salience-reminder null result, not evidence that the model cannot process current-cost facts.
5. The intervention is sensitive to task: Query00188 and Query00347 did not change under any arm, while Query00518/550/685/858 show varying responses.

### Not established

- This is not evidence of a psychological commitment effect. The plan is solver-supplied, not generated by the Agent.
- The experiment does not identify whether plan presence changes candidate generation, evaluation, or action selection internally.
- First-action outcomes do not establish full-trajectory completion or final path optimality.
- The eight tasks are reused from the existing paired-50 cohort, not a held-out independent test set. Repetitions are nested within tasks and are not independent samples.
- The task sample is too small for broad population-level claims or strong significance claims.

## Mechanism judgment and next step

The current evidence points away from a pure information-localization explanation and toward a plan-cue-dependent action-selection trade-off: showing the incumbent plan strongly supports RETAIN, but suppresses switching in cases where the incumbent first action is suboptimal. Removing the plan cue exposes alternatives but also causes unnecessary deviations when the incumbent remains optimal.

The next diagnostic should not be another generic prompt rewrite. It should separate:
1. **Candidate availability/consideration:** whether the model can identify a feasible alternative before choosing.
2. **Comparative evaluation:** whether it can rank the incumbent and alternatives using the same verified current-state values.
3. **Decision calibration:** whether it can retain when the incumbent is optimal and switch when an alternative is better.

Any candidate- or value-assisted condition must be explicitly labelled diagnostic/oracle-assisted, include both better and worse alternatives in randomized order, and preserve RETAIN controls. It must not be reported as a deployable method.

Before full continuation claims, run the pre-registered complete-continuation check on the two tasks fixed in the protocol, Query00188 and Query00347, across all four arms and both environments (16 trajectories). These two tasks are deliberately retained as the debug pair; report them as a limited execution-continuation diagnostic, not a representative sample. The current formal run only requested and executed one first tool action per trial.
