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

The current tool values are exposed in the native function descriptions. At the pinned CostBench revision, `Tool.generate_interface()` appends the current tool value to each tool description ([source](https://github.com/JiayuJeff/CostBench/blob/6424069f3f773ade076bcedbed302ed47cfb1837/env/core/base_types.py#L526-L532)). The system prompt asks the Agent to choose the lowest-total-cost path and adapt when tool properties change ([source](https://github.com/JiayuJeff/CostBench/blob/6424069f3f773ade076bcedbed302ed47cfb1837/env/run.py#L1604-L1630)).

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

## Cross-protocol evidence from native fact-update probes

The repository also contains small native continuation probes using **Agent-authored pre-event plans** and user-preference changes. These are not the same manipulation as the 50-task tool-value benchmark, so they are supporting mechanism evidence rather than a direct replication.

| Existing probe | Independent tasks | Main result |
|---|---:|---|
| Fact-salience re-audit | 4 | On SWITCH cases, first-action correctness rose from 2/4 with a minimal update to 4/4 with an explicit temporal correction. RETAIN preference decisions were 4/4 in both conditions; one explicit-update RETAIN arm made an invalid tool call. |
| Fact-link control | 4 | Minimal current-value wording: 2/4 correct SWITCH actions. “Changed from old value to new value” wording: 4/4. Adding an extra sentence linking the old preference object to the old value remained 4/4; it did not improve on the simpler correction wording. |
| EDR policy comparison | 4 | SWITCH first-action correctness was 2/4 for minimal facts, 4/4 for an explicit-delta prompt, and 4/4 for the provenance-derived EDR ledger. EDR did not outperform the simpler prompt baseline. |
| Action Guard comparison | 4 | SWITCH first-action correctness was 3/4 for minimal facts and 4/4 for both explicit-delta and Action Guard. The guard rejected two actions, but did not improve goal completion over the explicit-delta baseline. |
| Native candidate-identity control | 2 | The same-vs-different candidate manipulation produced identical outcomes: RETAIN 4/4 correct and SWITCH 0/4. Candidate identity did not change native first actions in this small control. |

The separate five-task candidate-conditioned **label-only** study found that a different but worse candidate could induce SWITCH responses, sometimes contradicting the model's own reported comparison. That result was not reproduced in the two-task native candidate-identity control and should remain exploratory rather than be treated as a stable mechanism.

The native fact-update evidence suggests that explicitly marking a fact as a correction from its previous value can improve the next tool action on a small development sample. It also shows that a provenance ledger or action guard has not demonstrated an advantage over a simple explicit-change prompt. Full records are linked in the [fact-salience audit](../../../research/plan_commitment_pilot/evidence/NATIVE_FACT_SALIENCE_AUDIT.json), [fact-link control](../../../research/plan_commitment_pilot/evidence/NATIVE_FACT_LINK_CONTROL.json), [EDR comparison](../../../research/plan_commitment_pilot/evidence/NATIVE_EDR_POLICY.json), [Action Guard comparison](../../../research/plan_commitment_pilot/evidence/NATIVE_ACTION_GUARD_AUDIT.json), [native candidate-identity control](../../../research/plan_commitment_pilot/evidence/NATIVE_CANDIDATE_IDENTITY.json), and [candidate-conditioned decision report](../../../research/plan_commitment_pilot/MECHANISM_DISCRIMINATION_NEW_RESULTS.md).

## Mechanism interpretation

Taken together, the evidence does **not** support one invariant “the Agent always clings to its plan” mechanism. It supports a narrower working hypothesis:

**Unstable evidence-conditioned plan revision, with incumbent persistence under implicit updates.**

1. In the 50-task tool-value benchmark, a solver-derived incumbent is supplied and the model is only told that the environment changed. It usually continues that incumbent, particularly when a better route must be reconstructed from tools outside the supplied suffix.
2. In small native preference-update probes, explicitly stating the old-to-new correction improves SWITCH first actions relative to a minimal current-value statement. This suggests the relationship between the new fact and the previous plan state matters.
3. In candidate-conditioned label-only prompts, a novel alternative can also induce over-switching to a worse candidate. The small native candidate-identity control did not reproduce that effect.
4. Once a path is selected, the 50-task native tool executions are reliable. The main error occurs in how the Agent maps new evidence to a continuation, not in executing a valid tool call.

This is a behavioral synthesis, not a claim about hidden model reasoning. The archived execution records retain tool calls and outcomes, not the model's full intermediate reasoning text. The preference-update probes use a different environmental fact from the tool-value benchmark and contain only four independent tasks each. They do not establish that explicit temporal wording is the cause of the 50-task RETAIN pattern.

## Next diagnostic probe

The next experiment should replicate the explicit-update effect in a fresh native cohort with **authentic Agent-authored pre-event plans**, rather than add another algorithm now.

- Select 8–10 independent native checkpoints with verified pre-event plans, balanced between RETAIN and SWITCH ground truth.
- **Baseline:** current minimal update message.
- **Explicit-update condition:** same checkpoint and current tool graph, but state the exact old-to-new fact or tool-value change. Do not suggest an alternative path.
- Keep state, tools, incumbent plan, and execution budget identical; randomize condition order and repeat each condition.
- Score the first native action, its arguments, native execution validity, and goal reach. Do not use the unchanged official final-answer scorer as the sole semantic measure for a changed preference.

A consistent improvement would justify implementing a minimal evidence-update mechanism and comparing it against the explicit-prompt baseline. EDR and Action Guard should remain out of the main method until they show an incremental benefit over that simpler baseline. Candidate-suggestion prompts should also remain out of this replication because they may create an over-switching cue.

This is a proposed next experiment, not an executed result. It requires new model calls and is intentionally not launched in this offline analysis.
