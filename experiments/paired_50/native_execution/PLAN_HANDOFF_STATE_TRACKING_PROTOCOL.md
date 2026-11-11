# Plan Handoff and State Tracking Diagnosis

## Status and precondition

**Frozen experimental design; no new model calls authorized by this document.** First run [attribute_execution_loss.py](attribute_execution_loss.py) on the **30 archived native trajectories** and inspect its action-level report. The 2×2 live-model experiment is a separate gate: do not launch it until the completed offline report is reviewed against this protocol.

This protocol uses **only `main`**. Reuse the same pinned native CostBench revision and original frozen checkpoints. All five diagnostic tasks were previously explored, so these are **development screening tasks, not unseen confirmation samples**.

**Research question:** Under the same post-action execution state and identical common first action, how do full replacement-plan handoff and explicit observed-state support, separately and jointly, affect the correctness of the LLM's subsequent tool execution?

## Stage 0: exact step-loss localization (offline)

On the existing 30 trajectories (5 base tasks × RETAIN/SWITCH × 3 first-action policies), evaluate every actually executed successful step with:

\[
\delta_t=c(s_t,a_t)+V^*(s_{t+1})-V^*(s_t).
\]

Here `s_{t+1}` must be **reconstructed from the recorded successful native tool observation**, updating the accumulated available types, rather than inferred from an ideal plan. Compute `V*(s_t)` and `V*(s_{t+1})` from the actual post-change tool graph using the same fixed values. Do not treat a different tool name or a different equally optimal path as a failure.

Require that every successful terminal trajectory satisfies:

\[
\sum_t\delta_t=\text{realized full-path regret}
\]

within numeric tolerance; stop on violation. Record first positive-loss step and action, first-action loss, later cumulative loss, observed tool result, repeated execution, whether a step contributes a new type, completion status, and alternative-branch decisions. Separate type-state evidence from richer semantic information in tool text: the current benchmark's typed graph does not represent every possible external state side effect. An apparently nonproductive type repeat is **descriptive**, not automatically an error.

**Do not use recorded original action regret alone** as a substitute for recalculating `V*(s_{t+1})`.

## Stage 1: common post-first-action checkpoint

For each selected task and environment:

1. Select one candidate first action with a frozen, common **non-experimental** rule: use the previously archived unrestricted graph-planner first action. This is deliberate planner-assisted **diagnosis**, not deployable performance. Include separate RETAIN and SWITCH conditions.
2. Fix that action's **native input arguments, exact native tool result, and prior observation history**. The source is the archived graph-planner first action from the successful [30-trajectory run](FULL_TRAJECTORY_COMPARISON_RESULTS.md), **not** an unconstrained new first step for each arm.
3. Reconstruct the original checkpoint at the pinned CostBench revision. Replay the *same* first action with its *same* argument JSON in a fresh isolated execution context. Compare the tool name, arguments, exact tool-result string, output type, and resulting accumulated typed state to the common source. Any mismatch blocks the affected task; never silently substitute another result.
4. Each A/B/C/D branch starts from an **independent fresh restored post-action environment**, with the same prefix history and no other branch's tool effects. The common first-action message and observation are identical across all four arms; model request histories differ **only** by the predeclared plan/state treatments.
5. The post-action plan supplied by the planner is computed from the **new, actual type-state after the common first action**, not from the initial environment checkpoint.

Do not claim that four calls with the same tool *name* alone are state-matched. Do not replay model tool calls from one branch as the underlying environment state of another without explicit state reconstruction and observation equality checks.

## Stage 2: fixed factorial prompt manipulations

All four conditions preserve the original user goal, native system instructions, tool interfaces, executed prefix and exact common first-action observation. They differ on precisely two factors:

| Arm | Active plan source | Explicit observed-state ledger |
|---|---|---|
| **A** | Previously supplied incumbent suffix, tagged as existing plan | Absent |
| **B** | Complete updated path from external planner, **explicitly designated as current**; old plan marked superseded | Absent |
| **C** | Original incumbent suffix, tagged as existing plan | Present |
| **D** | Complete updated path from external planner, **explicitly designated as current**; old plan marked superseded | Present |

A/C must not accidentally reveal the updated planner path. B/D must state: **“The current plan is externally planner-supplied. The former plan has been superseded.”** The earlier plan may remain visible in the earlier historical message, but may not be simultaneously called *the current plan*. If the planner determines that the old plan remains valid, B/D may legitimately retain a matching suffix; stratify no-change cases so this does not masquerade as a genuine handoff.

The updated plan is **privileged planning assistance**. B/D outcomes are *diagnostic upper-bound interventions*, not a deployable LLM-only policy result. The same planning assistance must be available to any information-matched planning baseline.

### Observed-state ledger

The C/D ledger is reconstructed **only from the actual jointly visible initial user information, replayed prefix history and genuine native tool observations**. It must be updated after each successful subsequent tool call by a fixed renderer declared before any trial. It preserves raw tool-call history.

Each ledger entry includes a source action and exact observation citation (in the model prompt this means an exact tool-call/observation identifier, **not** an answer key), one of:
- **Confirmed:** directly observed tool output or already observed typed-state fact.
- **Invalidated:** a previously confirmed claim contradicted by a later observed tool result; include both source identifiers.
- **Unknown:** facts that have not been observed or cannot currently be established. An unknown fact is not automatically valid.

Do not read simulator hidden state, ground-truth labels, oracle values, shortest-path optimal next steps, or future events to populate the ledger. In the existing typed CostBench environment, when an observation does not support a semantic fact, simply state it as unknown rather than inferring it.

A/C and B/D must use the same tool-response serialization, context-length limits and native tool execution environment. Log the raw history and ledger separately so any observed C effect can be distinguished in later follow-ups from mere summarization or salience.

## Stage 3: control arms and common execution protocol

In addition to A/B/C/D, evaluate:

1. **Fixed-plan executor:** an external controller selects the next tool from the updated full plan after each successful native observation; **the same DeepSeek model supplies only the required arguments** via a single-tool function schema. Verify actual tool result and state at each step. No prefilled correct arguments.
2. **Per-step graph replanner:** recompute the next tool from the current *observed* typed state after each call; same LLM generates arguments, same tool observation and goal-check logic. Do not use future hidden states or the official evaluation solver for control.
3. **Optional separate scripted path replay** may check environment feasibility with generated deterministic arguments, but must be labeled an environment sanity test and **not** substituted for the argument-matched controller comparison.

For all arms report number of LLM requests, provider tokens, executed tool count, native validity, goal reached, full-path optimality, first positive-loss step, total Bellman loss, and elapsed time.

## Interpretation and explicit factorial test

Primary descriptive outcome: within-condition per-task **complete-path optimality** and realized full-trajectory regret, with goal-reaching and validity reported separately. Five tasks are too small for strong inferential claims.

- B better than A: supplying and handing off a complete updated plan helps **in this interface**. It does **not** isolate the effect of removing old-plan salience.
- C better than A: explicitly presenting observed-state facts helps. This does **not** show hidden model state tracking was wrong; salience, formatting and compression remain alternatives.
- D better than B and C: both aids combined perform best, **not necessarily synergistically**.
- For any scalar higher-is-better Y, the additive factorial interaction is `I = Y_D - Y_B - Y_C + Y_A`. Report per-task values and interaction; no causality claim for tiny samples.
- If D remains suboptimal while fixed-plan controlled execution is optimal, the evidence points toward **action-choice/execution adherence under this interface**, not necessarily a general state-management deficit.
- If per-step graph replanning or a simple controller already resolves the failures, **stop**: a more complex algorithm is unnecessary on the tested full-information CostBench task family.
- If B provides gains, only then consider a **separate** contrast holding the updated full plan fixed and varying whether the old plan is explicitly tagged superseded.

No new hidden intervention, ablation or goal may be introduced after inspecting outcomes without labelling it an exploratory follow-up.

## Decision gate before paid models

Freeze the common-first-action source IDs, tool arguments, native result hashes, post-action state hashes, each of the four prompt templates, ledger update function, controller rules, task inclusion and per-task scoring ahead of provider calls. Dry-run and unit test the four independent environment restorations to verify exactly matched starting state and identical common observation.

**Stop without running the 2×2 if** the 30-trajectory loss audit fails telescoping, post-action source traces cannot be reproduced, current tool interfaces are not equivalent, or the ledger needs hidden oracle values. Keep the entire result in the existing repository `main`; create no branches.

## Subsequent publication direction

Only after the 2×2 reveals a remaining failure should we consider (i) incomplete/partially observed events beyond CostBench, or (ii) a selective update-scope selector. Graph dependence and plan repair alone are classical planning baselines, not automatic novelty claims.


## Offline implementation freeze addendum

### Common-action restoration result

The restoration preflight is complete and passed: **10 task/environment checkpoints × 4 independent OS processes = 40 native replays**. All 40 replayed the exact archived graph-planner first-action arguments and reproduced the exact archived native tool-result string; the post-action typed-state hash matched across all four restorations for each of the ten checkpoints. The check used zero provider calls. See the `common-action-restoration-preflight` artifact from the pinned GitHub Actions validation run.

This certifies the native action/result/state handoff under the pinned CostBench snapshot. It does not mean the four prompt variants have been run or evaluated.

### Archived assistant content normalization

The archived full-trajectory records retain the first tool name, exact argument string, exact native result, and checkpoint hash, but do **not** retain the assistant's free-form text accompanying that first tool call. Therefore the post-action continuation history uses a normalized assistant tool-call message with `content: null` in **all four arms**. The exact archived tool arguments and tool observation are retained. This limitation is explicit; the experiment must not be described as reproducing the original assistant reasoning text.

### Frozen prompt matrix

The offline prompt builder is [`prepare_plan_handoff_experiment.py`](prepare_plan_handoff_experiment.py). It creates the same post-action conversation history and native tool schemas for all arms, then adds one standardized post-action user message containing two fixed sections:

- **Plan handoff:** A/C receive no replacement path; the original plan remains visible in the preceding history. B/D receive the complete continuation recomputed by the unrestricted typed-graph Dijkstra planner from the actual post-action type-state, and the earlier plan is explicitly marked superseded.
- **Observed-state ledger:** A/B receive no separate ledger. C/D receive a deterministic ledger containing only checkpoint-visible types and the exact common native observation, with source/action identifiers.

The ledger renderer records confirmed facts, an empty invalidated set unless an explicit contradiction is observed, and unknown semantic facts. The current CostBench typed state is monotonic, so the renderer **does not infer invalidation** from the addition of another type. After each later successful native action, `update_ledger` appends the newly observed output type and exact observation; failed actions add an unknown state effect instead. This is an observable typed-state ledger, not a general semantic world-state tracker.

The post-action message in every arm also states that the common first action has already completed and must not be repeated. All arms receive the same native tool definitions, goal, original request, prefix, common action, exact result, model settings and output limit.

### Development-screen run matrix and model freeze

The offline builder creates **5 previously explored tasks × 2 environment conditions × 4 arms × 2 repetitions = 80 continuation requests**. These are development-screen tasks, not an unseen confirmation set. The frozen model configuration is `deepseek-flash`, temperature 0, thinking disabled, and 2,048 maximum output tokens per call.

The builder reports the harness's conservative `reservation_units` (serialized request bytes plus output allowance and fixed buffer). These units are a request-budget reservation measure, **not a claim about actual tokenizer tokens**. No model call is made by prompt preparation. Review the generated request count and reservation total before any paid run.

The 2×2 prompt preflight must pass all of the following for every task/environment cell: identical common-history hash across A/B/C/D; identical tool-schema hash; four distinct prompt hashes; balanced plan-handoff and ledger treatment flags; matching restoration, argument, result and post-action state hashes. Any mismatch blocks the live experiment.

**Current gate:** native common-action restoration passed. Prompt construction and ledger-renderer tests are the next offline gate. No paid model experiment is authorized by this addendum.
