# Mechanism analysis: incumbent persistence in native execution

**Status:** Completed offline analysis of the frozen 50-task cohort. No additional model calls were made.

## Scope and evidence separation

The primary cohort contains 50 independent CostBench base tasks, each evaluated under matched RETAIN and SWITCH conditions (100 native trajectories). The provider-reported model was DeepSeek Flash, temperature 0, with thinking disabled.

The incumbent suffix in this benchmark is **solver-derived and supplied to the model at the checkpoint**. It is not a plan independently authored by the model. The result therefore measures incumbent-conditioned behavior under a controlled supplied-plan protocol; it does not by itself establish a self-generated plan-commitment effect.

The separate 67-event audit recovered 27 authentic pre-event model-written plans from 67 checkpoints. Its 22 RETAIN and 5 SWITCH counts are outputs of a deterministic evidence gate, with zero new post-event model calls; those counts are not model behavior. A separate extraction from the original official dynamic-run JSON shows that the actual model's first post-event action followed its own incumbent in 27/27 cases. That original-action result is reported below and is not derived from the gate replay.

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

A second offline stratification separates **where** the changed incumbent tool occurs in the supplied suffix:

| Changed-tool position in incumbent | Tasks | Followed incumbent | Value-optimal |
|---|---:|---:|---:|
| First and only action | 12 | 10 | 2 |
| First action of a multi-action suffix | 5 | 5 | 0 |
| Later action in incumbent suffix | 9 | 9 | 0 |
| Tool outside incumbent suffix | 24 | 24 | 0 |

Both successful departures occur in the first-and-only-action group (Query00440 and Query00662). When the changed tool is the first action but the incumbent has further steps, the model retains in all five cases. It also retains in all nine cases where the changed tool occurs later in the incumbent. This narrows the descriptive pattern: the two observed deviations are confined to single-action incumbents, where there is no multi-step supplied suffix to continue.

The split is generated by [`analyze_mechanism_strata.py`](analyze_mechanism_strata.py), which validates frozen request hashes, checkpoint hashes, paired incumbent suffixes, tool schemas and the single-tool-value change before writing the per-task table. Its unit tests are in [`test_mechanism_strata.py`](test_mechanism_strata.py). The complete offline workflow, including this stratification, passed in [GitHub Actions run 42636127223](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42636127223). The run artifact contains `mechanism_strata/summary.json` and `mechanism_strata/switch_strata.csv`.

This finer split remains post-hoc and does not establish why the model behaves this way. In particular, it cannot distinguish anchoring on the supplied suffix from failure to identify or compare alternatives in the current tool graph.

## Original native-agent behavior with Agent-authored plans

The 80-task official dynamic baseline contains 67 observed environment-change events. Among these, 27 cases have a uniquely recoverable Agent-authored pre-event plan. I extracted the actual post-event tool calls from each original `conversation_history`, using the recorded event step to separate pre-event and post-event calls.

| Measure | Result |
|---|---:|
| Pre-event executed prefix matches the Agent-authored plan | 27/27 |
| Actual first post-event action follows the incumbent | 27/27 |
| Actual first post-event action matches the current optimal first action | 15/27 |
| Actual first action differs from the current optimal first action | 12/27 |
| Complete actual suffix equals the incumbent suffix | 23/27 |
| Complete actual suffix equals the current optimal suffix | 15/27 |
| Original trajectories reach the goal | 27/27 |
| Official final answers accepted | 24/27 |

The deterministic evidence gate labels 22 of these cases RETAIN and 5 SWITCH under its 0.25 switch penalty. In the five gate-SWITCH cases, the original model's first post-event action still follows the incumbent in **5/5** cases and matches the current optimal first action in **0/5**. Three of those five execute the exact old suffix; the other two change later actions but still do not execute the current optimal suffix.

This is direct evidence of incumbent persistence in the original native Agent traces, where the pre-event plan was written by the model itself. The 27 cases are a selected subset of the 67 event checkpoints, not a held-out sample. The 22/5 gate labels remain deterministic comparator outputs, not model-generated labels. See the [reproducible original-agent audit](../../../research/costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json).

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

Taken together, the evidence supports a working hypothesis of **unstable evidence-conditioned plan revision, with strong incumbent persistence when the update is implicit**.

1. The strongest direct native evidence is the original 27-plan subset: the model's first post-event action followed its own pre-event plan in 27/27 cases. In the five cases where the independent gate selected SWITCH, the model still followed the incumbent first action in all five.
2. The 50-task paired benchmark reproduces the same pattern under a solver-supplied incumbent: 48/50 SWITCH-condition trajectories execute the exact incumbent suffix. The model rarely discovers an alternative outside that suffix.
3. Small native preference-update probes suggest that explicitly stating an old-to-new correction can improve SWITCH first actions relative to a minimal current-value statement. EDR and Action Guard did not outperform that simpler prompt baseline.
4. Candidate-conditioned label-only prompts can induce over-switching to a worse candidate, but this was not reproduced in the small native candidate-identity control. It remains exploratory.
5. Once a path is selected, native tool execution is generally successful. The dominant issue is how new evidence is translated into the next action, not whether a selected tool can execute.

This is a behavioral synthesis, not a claim about hidden model reasoning. The original 27-plan subset is selected from a development cohort; the 50-task benchmark uses solver-derived incumbents; and the preference-update probes use a different type of environmental fact and only four independent tasks each. Together they identify a reproducible action-level asymmetry, but do not yet isolate a single causal mechanism.

## Subsequent continuation diagnostic

The 30-trajectory action-loss audit motivated a five-task plan-handoff × observed-state 2×2 development screen. It completed 80/80 native continuations from matched post-prefix checkpoints.

- With the original incumbent only (A/C), optimal continuations were 5–6/10 in RETAIN and 6/10 in SWITCH.
- With the complete current graph-planner continuation (B/D), optimal continuations were 10/10 in both RETAIN and SWITCH.
- B and D executed identical continuation action sequences in all 20 matched task/repetition cells. The explicit typed-state ledger did not add an observed benefit once the complete continuation was supplied.
- The independent unit is five base tasks. The 80 trajectories are paired conditions and repetitions, not 80 independent tasks.
- The common first action was fixed; the result isolates continuation after that prefix. B/D are externally planner-assisted diagnostic conditions, not LLM-only methods.

The [full report](PLAN_HANDOFF_STATE_TRACKING_RESULTS.md) records task-level contrasts, Bellman checks, timing and limitations. The fixed-plan executor and per-step graph-replanner controllers specified in the broader protocol were not included.

## Next diagnostic probe

The next focused contrast is the checkpoint-level plan-status annotation study. Both arms receive the same frozen checkpoint and complete graph-planner continuation; only the prior-plan status changes from UNSET to VALID/STALE. Its 10-task cohort and 80-request matrix passed offline preflight in [run 43006621052](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43006621052), with zero provider calls. The frozen manifest is [PLAN_STATUS_CONFIRMATION_MANIFEST.json](PLAN_STATUS_CONFIRMATION_MANIFEST.json). The paid confirmation job was skipped and has not been launched.

This follow-up remains an oracle-assisted diagnostic, not a deployable method. No new algorithm is proposed at this stage.
