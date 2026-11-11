# Stepwise Native Execution Loss Attribution

## Outcome and next experimental implication

**The actual-point-of-loss audit succeeded on all 30 archived native trajectories, with no new DeepSeek calls.** It distinguishes first-action loss from subsequent execution loss using a Bellman value difference at the **actual resulting type-state after each successful native tool call**, rather than comparing action names to a single ideal path.

In the unrestricted graph-planner arm, **0/10 trajectories incurred loss in their first action**, yet **3/10 incurred positive loss beginning at their second action**. This provides a directly measured reason to test *complete plan handoff* and *observed-state presentation* during subsequent execution. It does **not** establish either as the mechanism.

## Source, execution and verification

- [Pinned offline GitHub Actions run #42977711327](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42977711327): all native validation steps succeeded.
- [Action-level state transitions, observations and loss decomposition](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42977711327/artifacts/13836251817), artifact `native-step-loss-attribution`.
- [Original 30 model-executed trajectories](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42974338707/artifacts/13834887461), artifact `native-full-trajectory-comparison`.
- Reproduction script: [`attribute_execution_loss.py`](attribute_execution_loss.py). Coverage: five original basic tasks × RETAIN/SWITCH × incumbent / candidate_gate / graph_planner = 30 independent *trajectory executions* from **five** independent base tasks.
- **Provider calls: 0.** Revision and native type graph are the pinned CostBench study configuration. All 30 successful trajectories passed type-feasibility, exact recorded cost agreement, and value-telescoping checks.

For each step:

\[
\delta_t = c(s_t,a_t) + V^*(s_{t+1}) - V^*(s_t).
\]

`s_{t+1}` is the **observed successfully executed tool output projected into the available-type state**, not the state predicted by an intended plan. `V*(s)` is recomputed on the same frozen current native tool-value graph. The `V*` used here is a diagnostic external reference, **not a controller input**. A changed tool name is not counted as loss if it preserves an optimal remaining path; only positive `delta_t` indicates a realized excess-value contribution under this deterministic type-graph model.

For every complete trajectory, `sum(delta_t)` matches the archived realized full-path regret within tolerance. A positive loss is reported without treating a different but equal-optimal path as a failure. No hidden simulator state or unobserved future outcome was consulted in preparing model-facing data (there was no model-facing data in this audit).

## Aggregated outcomes

| Policy | Native trajectories | First-action positive loss | Later-action positive loss | First-action loss sum | Later-action loss sum | Total |
|---|---:|---:|---:|---:|---:|---:|
| Incumbent first action, free continuation | 10 | 5 | 0 | 6.50 | 0.00 | **6.50** |
| Candidate + bounded verifier, free continuation | 10 | 4 | 1 | 3.91 | 1.72 | **5.63** |
| Full graph-planner first action, free continuation | 10 | **0** | **3** | **0.00** | **3.48** | **3.48** |

All 30 native trajectories reached the goal. None repeats the same tool name in a trajectory or calls an action with an already-available output type in the reconstructed type graph. In all four cases where the candidate gate had first-step loss, there was no later positive loss. In its one later-loss case, the first action incurred zero loss.

**The graph-planner arm's three first positive-loss steps are all step 2.** No loss attributable to the graph-planner first action was detected in any of its 10 trajectories.

## Task-level action loss

The following contains every **positive-loss trajectory** (RETAIN conditions and optimal SWITCH conditions have no positive loss). Figures are path-regret contributions, not deviations from the spelling of any reference plan.

| Task | Environment | Policy | First positive-loss step | First-action loss | Later loss | First loss-generating action |
|---|---|---|---:|---:|---:|---|
| Query00178 | SWITCH | Incumbent | 1 | 1.30 | 0.00 | `Transportation_Search_to_Final_4Steps` |
| Query00178 | SWITCH | Candidate gate | 1 | 1.30 | 0.00 | `Transportation_Search_to_Final_4Steps` |
| Query00178 | SWITCH | Graph planner | **2** | 0.00 | **1.58** | `Transportation_Refine_to_Step2` |
| Query00351 | SWITCH | Incumbent | 1 | 1.30 | 0.00 | `Accommodation_Refinement_Step1` |
| Query00351 | SWITCH | Candidate gate | 1 | 1.30 | 0.00 | `Accommodation_Refinement_Step1` |
| Query00549 | SWITCH | Incumbent | 1 | 1.30 | 0.00 | `Search_Attraction_Candidates` |
| Query00549 | SWITCH | Candidate gate | 1 | 1.30 | 0.00 | `Search_Attraction_Candidates` |
| Query00549 | SWITCH | Graph planner | **2** | 0.00 | **0.18** | `Attraction_Refinement_Step2` |
| Query00689 | SWITCH | Incumbent | 1 | 1.30 | 0.00 | `Dining_Search_to_Final_4Steps` |
| Query00689 | SWITCH | Candidate gate | **2** | 0.00 | **1.72** | `Dining_Refinement_Step1` |
| Query00689 | SWITCH | Graph planner | **2** | 0.00 | **1.72** | `Dining_Refinement_Step1` |
| Query00851 | SWITCH | Incumbent | 1 | 1.30 | 0.00 | `Shopping_Search_to_Final_4Steps` |
| Query00851 | SWITCH | Candidate gate | 1 | 0.01 | 0.00 | `Shopping_Search_Planning_to_Step2` |

**The most informative subset for the next 2×2 experiment is Query00178, Query00549 and Query00689 (SWITCH)**: the initial graph-planner action was optimal, but the LLM's second action was not. The paired RETAIN conditions remain necessary to check unnecessary changes.

## Mechanism limits and decision

This audit is **typed-state-level** Bellman attribution. It captures only states represented by the CostBench tool dependency graph and the successful outputs' declared output types; the raw observation strings are preserved for scrutiny, but there is not yet a general semantic state tracker or hidden state comparison. Positive loss at step 2 is an **observable execution decision failure** under this graph, not proof that the LLM had an incorrect private state.

An updated complete graph-planner path was *not* delivered to the model in the previous full-trajectory experiment; only its first action was controlled. Therefore do not claim any failure in following a properly handed-off new plan. The pre-registered next experiment [`PLAN_HANDOFF_STATE_TRACKING_PROTOCOL.md`](PLAN_HANDOFF_STATE_TRACKING_PROTOCOL.md) tests **plan handoff × observed-state ledger** from identical replayed first-action arguments and exact tool result, with independent environment restoration and same-model argument-generation controls.

**Decision: GO for offline matched-checkpoint restoration preflight, but NO authorization yet for new paid model experiments.** If the common action or observation cannot be reproduced identically, stop instead of masking the mismatch with a prompt adjustment.
