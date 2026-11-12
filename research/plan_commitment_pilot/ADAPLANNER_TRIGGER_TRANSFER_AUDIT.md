# AdaPlanner Trigger Transfer Audit

**Status:** offline development audit; zero provider calls; no validation or test tasks accessed.

## Research question

Can AdaPlanner's feedback-triggered refinement be extended to detect a plan that remains executable and completes the task, but whose assumptions or decision quality have changed after an environment update?

## What AdaPlanner actually triggers on

The official ALFWorld implementation is broader than an Assertion-Failure-only description:

1. The generated `solution()` executes with assertions written at planned steps.
2. `capture_output()` catches execution exceptions, including assertion failures, and records the local variables at the failing checkpoint.
3. If `agent.is_success` is true, execution stops.
4. If the function returns without an exception but the task is still incomplete, the runner creates an explicit feedback message stating that execution completed but the task did not.
5. The model receives the error/feedback, revises the code, and chooses a resume step. The runner allows six attempts and returns to step 1 after the first three attempts.

Therefore, AdaPlanner's practical trigger is **execution exception/assertion or task non-completion**. A successful action sequence with a stale plan assumption does not necessarily activate it.

Sources: [AdaPlanner ALFWorld runner](https://github.com/haotiansun14/AdaPlanner/blob/main/ALFWorld/alfworld.ipynb), [AdaPlanner prompts](https://github.com/haotiansun14/AdaPlanner/blob/main/ALFWorld/prompt.py).

## Cross-benchmark audit

CostBench does not record AdaPlanner's generated Python assertions, expected-observation assertions, or code checkpoints. The following is consequently a conservative observable proxy, not a faithful replay of AdaPlanner.

The proxy fires when either:
- a post-event native tool output contains a clear execution-error marker; or
- the native task goal is not reached.

The audited population contains 27 uniquely recoverable Agent-authored plans from 67 observed dynamic events in the official 80-task development population. Every selected event is a `cost_change` event; event timing is after one or two tool calls.

| Measure | Result |
|---|---:|
| Recoverable Agent-authored plans | 27 |
| Cost-change events | 27/27 |
| Incumbent plans still feasible under updated tools | 27/27 |
| Post-event native tool-error outputs | 0 |
| Native goals reached | 27/27 |
| Failure/non-completion proxy would trigger | **0/27** |
| Original Agent first action follows its incumbent | 27/27 |
| Original first action matches the current graph-optimal first action | 15/27 |
| Positive full-continuation objective gap | 13/27 |
| Gap exceeds the pre-existing 0.25 decision margin | 5/27 |

The original Agent follows its incumbent first action in all 27 cases. In the five cases where the existing graph audit selects SWITCH, the original first action follows the incumbent in 5/5 and matches the current graph-optimal first action in 0/5.

The distinction between first-action mismatch and full-path objective gap matters: 12/27 first actions differ from the selected graph-optimal first action, while 13/27 incumbent suffixes have a positive full-path gap. These are not interchangeable measures.

The existing graph audit classifies 22/27 as RETAIN and 5/27 as SWITCH using its previously frozen margin. Of the 13 positive-gap cases, eight remain within that margin and five exceed it. This is retrospective graph evidence, not a newly tested model policy.

Reproducible records: [JSON](evidence/ADAPLANNER_TRIGGER_TRANSFER_AUDIT.json), [CSV](evidence/ADAPLANNER_TRIGGER_TRANSFER_AUDIT.csv), [audit script](audit_adaplanner_trigger_transfer.py).

## What the audit says about the trigger

Two simple trigger variants are inadequate:

- **Failure-only trigger:** misses all 27 selected cases because every task completes without a post-event tool error. It therefore misses the five cases that exceed the existing decision margin.
- **Any-environment-change trigger:** fires on all 27 cases. This detects the event but is not selective and does not distinguish a still-appropriate plan from a plan whose ranking has changed.

The missing signal is not merely feasibility. All 27 incumbent plans remain executable. The relevant distinction is between **hard invalidation** and **soft plan-quality drift**:

- Hard invalidation: an action becomes unavailable, its input/output contract changes, a precondition fails, or an assertion fails.
- Soft plan-quality drift: the incumbent remains executable, but facts used to compare it with alternatives have changed.

## Revised trigger hypothesis

Do not adopt the earlier single scalar `D_t > θ` yet. The current evidence does not justify an arbitrary scalar or threshold. A more testable two-stage trigger is:

\[
T_t = H_t \;\lor\; \left(\Delta F_t \land \neg C_{\mathrm{retain}}(P_t,S_t)\right)
\]

where:

- \(H_t\) is AdaPlanner's existing execution-failure or subgoal-noncompletion signal.
- \(\Delta F_t\) indicates that facts in the current plan's *decision-relevant dependency graph* have changed. This must include facts that can change the ranking of feasible alternatives, not only facts attached to the incumbent tool sequence.
- \(C_{\mathrm{retain}}\) is a conservative certificate that the incumbent remains feasible and within a pre-frozen acceptance margin under the updated facts.

If the certificate succeeds, keep the incumbent and continue in-plan. If it fails or cannot be established, invoke AdaPlanner's existing Out-of-plan Refiner. The incumbent remains visible as evidence; the trigger does not automatically switch plans or hide the old plan.

This design is consistent with the earlier mechanism findings:
- Removing the incumbent plan cue improved some SWITCH decisions but harmed RETAIN decisions ([plan-cue study](../../experiments/paired_50/native_execution/MECHANISM_STUDY_FINAL_REPORT.md)).
- Presenting a different but feasible, worse candidate induced over-switching in the controlled development probe ([candidate-identity study](MECHANISM_DISCRIMINATION_NEW_RESULTS.md)).

Thus, the next method should revalidate the incumbent against current evidence rather than simply remove it or introduce a novel candidate.

## Decision

**GO:** implement an offline, public-information-only prototype of the two-stage trigger and evaluate its false-trigger and missed-trigger behavior on existing development checkpoints.

**NO-GO:** do not claim an AdaPlanner improvement yet, do not call the graph-reference result a deployable trigger, and do not start paid model execution. The present evidence establishes a trigger gap in this CostBench development subset; it does not establish the effectiveness of the proposed trigger.

## Next offline step

Reconstruct the plan-dependency snapshot at plan-creation time, compare it with the post-event public tool interface, and test whether a conservative retain certificate can distinguish the 5 high-margin SWITCH references from the 22 RETAIN references without using the current exact optimum as an input.
