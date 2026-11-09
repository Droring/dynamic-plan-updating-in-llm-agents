# Mechanism analysis: incumbent persistence in native execution

**Status:** Completed offline analysis of the frozen 50-task cohort. No additional model calls were made.

## Scope and evidence separation

The primary cohort contains 50 independent CostBench base tasks, each evaluated under matched RETAIN and SWITCH conditions (100 native trajectories). The provider-reported model was DeepSeek Flash, temperature 0, with thinking disabled.

The incumbent suffix in this benchmark is **solver-derived and supplied to the model at the checkpoint**. It is not a plan independently authored by the model. The result therefore measures incumbent-conditioned behavior under a controlled supplied-plan protocol; it does not by itself establish a self-generated plan-commitment effect.

The separate 67-event native audit has a different role. It recovered 27 authentic pre-event model-written plans from 67 checkpoints. Its 22 RETAIN and 5 SWITCH counts are outputs of a deterministic evidence gate, with zero new post-event model calls. Those counts are not model behavior and are not pooled with the 50-task study.

## What the model receives

The native runner starts a fresh conversation with the original CostBench system prompt and a checkpoint message containing:

- the original user request;
- the completed prefix tool and its observation;
- the current available type state;
- the incumbent remaining suffix, explicitly described as selected before the environment update;
- an instruction that the tool environment has changed and the model may continue or choose another feasible continuation.

The current tool values are exposed in the native function descriptions. At the pinned CostBench revision, `Tool.generate_interface()` appends the current tool value to each tool description ([source](https://github.com/JiayuJeff/CostBench/blob/6424069f3f773ade076bcedbed302ed47cfb1837/env/core/base_types.py#L526-L532)). The system prompt asks the Agent to choose the lowest-total-value path and adapt when tool properties change ([source](https://github.com/JiayuJeff/CostBench/blob/6424069f3f773ade076bcedbed302ed47cfb1837/env/run.py#L1604-L1630)).

The model is **not** given a structured old-value/new-value event record or the identity of the changed tool. It must use the current tool descriptions and dependency graph to reconsider the continuation.

## Main behavioral findings

### Structured decision evaluation

| Measure | Result |
|---|---:|
| RETAIN accuracy | 48/50 (96%) |
| SWITCH accuracy | 3/50 (6%) |
| Paired accuracy | 1/50 (2%) |
| Balanced accuracy | 51% |

The model strongly defaults to RETAIN even when asked to make an explicit RETAIN/SWITCH judgment.

### Native tool execution

| Measure | RETAIN condition | SWITCH condition |
|---|---:|---:|
| First action followed incumbent | 48/50 (96%) | 48/50 (96%) |
| First-action decision accuracy | 48/50 (96%) | 2/50 (4%) |
| Executed path value-optimal | 48/50 (96%) | 2/50 (4%) |

All 100 first tool actions succeeded and all 100 trajectories reached the goal. The issue is therefore not a failure to execute a selected tool or complete the task.

The paired first-action patterns were:

| RETAIN arm / SWITCH arm | Pairs |
|---|---:|
| RETAIN / RETAIN | 47 |
| RETAIN / SWITCH | 1 |
| SWITCH / RETAIN | 1 |
| SWITCH / SWITCH | 1 |

Only one pair changed in the expected direction. One pair changed in the opposite direction, and 48/50 pairs made the same first-action decision under both conditions. The two SWITCH-arm deviations from the incumbent were both path-optimal, but one of them also switched in its RETAIN arm. Thus only one pair demonstrates condition-sensitive adaptation.

## Where the persistence appears

The 50 SWITCH conditions were split by the location and direction of the single changed tool value. Pair validation confirmed that each arm used the same checkpoint, incumbent suffix and tool schemas, and that exactly one tool value differed.

| SWITCH-condition change | Tasks | Followed exact incumbent | Alternative path | Value-optimal alternatives |
|---|---:|---:|---:|---:|
| Incumbent tool increased | 26 | 24 | 2 | 2 |
| Tool outside incumbent decreased | 24 | 24 | 0 | 0 |

The two alternative paths occurred only when the changed tool was the **first and only action** in the incumbent suffix. Across the 12 tasks with that structure, the model switched in two and retained in ten. It did not switch when the changed incumbent tool appeared later in a multi-action suffix, nor in any of the 24 cases where a tool outside the incumbent became more attractive.

This is a descriptive, post-hoc split rather than a randomized mechanism test. It suggests that the model is more likely to react to a direct change in its immediate incumbent action than to discover a newly preferable alternative elsewhere in the tool graph.

## Where path regret enters

For the 50 SWITCH conditions, total path regret was 62.40 units:

- First-action regret: 52.16 (83.6%).
- Later-action regret: 10.24 (16.4%).

For the 24 outside-alternative-decrease cases, 29.90 of 31.20 regret units (95.8%) arose at the first action. This points to a failure to select a new continuation at the checkpoint, rather than a failure to execute a newly selected path.

## Mechanism interpretation

The evidence supports the following working explanation:

**Incumbent-anchored counterfactual path regeneration failure.**

1. The supplied incumbent is a salient, immediately executable continuation.
2. Although current tool values are visible, the model receives no explicit event diff. It must identify the relevant change and reconstruct alternatives from the current type-dependency graph.
3. It usually preserves the incumbent, especially when the improvement is in a tool outside that suffix. Direct deterioration of the first and only incumbent action is the only stratum in which any SWITCH-arm deviations appear.
4. Once a path is selected, native tool execution is reliable. The dominant error is the decision to update the continuation, not tool execution.

This is a behavioral explanation, not a claim about hidden model reasoning. The archived execution records retain tool calls and outcomes, not the model's full intermediate reasoning text. The current evidence cannot separate incumbent anchoring from weak alternative-path enumeration or insufficient salience of the environmental change.

## Next diagnostic probe

Before designing an intervention, the smallest useful follow-up is a controlled prompt ablation on a small, frozen subset of the existing tasks. It should compare:

- **Baseline:** current checkpoint prompt with the incumbent suffix and no explicit change diff.
- **Explicit-diff condition:** same prompt, but identify the changed tool and show its previous and current value.
- **No-incumbent condition:** same current state and current tool definitions, but omit the supplied incumbent suffix.

Interpretation:

- Improvement only with the explicit diff points to change-detection or event-salience failure.
- Improvement only when the incumbent is hidden points to incumbent anchoring.
- Failure in all three conditions points toward general alternative-path generation or comparison.

This probe is a proposed next experiment, not an executed result. It requires new model calls and is intentionally not launched in this offline analysis.
