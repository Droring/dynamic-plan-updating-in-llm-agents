# First algorithm-development iteration: evidence refresh and pre-action guard

**Status:** Both prototypes implemented, unit-tested and run against real native CostBench execution. **NO-GO for an empirical improvement claim.** Do not silently delete negative evidence.

## Research target
Make a tool Agent respond reliably to updated factual evidence after its own prior planning and partial execution. Reward correct selective continuation when a fact stays unchanged, correct fresh tool use when a relevant fact changes, and actual successful/valid tool execution. **This is not a tool-cost optimization project**.

## Prototype 1: Evidence-Dependency Refresh (EDR)
- Source: [evidence_dependency_refresh.py](evidence_dependency_refresh.py), with [5 offline tests](test_evidence_dependency_refresh.py).
- Compare the current user-supplied TransportationStyle to prior **real assistant tool-call argument**. Mark dependent preference object unchanged, changed, or unknown. Use the discovered provenance to construct a factual note, not a gold action.
- Actual native DeepSeek Flash pilot: [CI #42449416380](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42449416380), independently reaudited [#42449659858](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42449659858).
- 4 historical development tasks × 2 factual conditions × 3 arms = **24 native trajectories**, 84 provider calls.
- RETAIN first decision 4/4; SWITCH first decision 4/4. This equals an ordinary explicit-change prompt baseline.
- Strict complete-without-tool-error: EDR RETAIN **3/4**, SWITCH **2/4**; explicit prompt RETAIN **3/4**, SWITCH **3/4**. Therefore EDR is not an improvement.

## Prototype 2: Bounded pre-action evidence guard
- Source: [action_evidence_guard.py](action_evidence_guard.py), with [7 guard tests](test_action_evidence_guard.py) (plus 5 EDR tests).
- Controller intercepts proposed native tool calls before CostBench executes them, checks **observed fact provenance** and **required available input types**, and blocks a stale or invalid proposed action. It requests at most **one** evidence-based correction from the model without executing rejected actions. If another invalid action is proposed, it fails closed. It does not inject a correct tool name, optimal path or target final answer.
- It is a concrete execution intervention, unlike EDR's evidence note, but remains narrowly implemented for `TransportationStyle` and CostBench's transportation tools.
- Actual native trial: [CI #42449991199](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42449991199), independently reaudited [CI #42450236273](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42450236273).
- Four **previously studied development tasks** × RETAIN/SWITCH × minimal fact/explicit fact/action guard = **24 native trajectories**, 84 DeepSeek provider calls.
- Guard actually rejected **2 proposed actions in SWITCH**, charged **2 extra feedback calls**, and never rejected a RETAIN proposal.
- The earlier initially failed workflow [#42449884598](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42449884598) stopped before paid calls because the invocation requested a five-call cap while the argument parser still accepted four; this was repaired before the actual scored experiment.

### Verified action-guard outcomes

| Condition | RETAIN correct first decision | SWITCH correct first decision | RETAIN strict complete (no native tool error) | SWITCH strict complete (no native tool error) |
|---|---:|---:|---:|---:|
| Minimal current-value statement | 4/4 | 3/4 | 4/4 | 3/4 |
| Ordinary explicit delta prompt | 4/4 | **4/4** | 4/4 | **3/4** |
| **Pre-action guard** | 4/4 | **4/4** | 4/4 | **3/4** |

The guard eliminates one observed wrong SWITCH first action relative to minimal statement and avoids executing two invalid/stale proposals. **It does not improve strict completion over the simple explicit-delta prompt baseline.** Guard protection may convert a failed tool action into a model response with no executed goal-reaching continuation, which is a failure on end-to-end completion.

The execution comparison is on the same four exploratory tasks used during mechanism diagnosis, **not held-out independent validation**. Across provider sessions, exact stochastic model behavior may vary despite temperature 0. Do not combine these 24 arms with the 24 EDR arms as 48 independent tasks.

Critically, these strict completion measurements refer to reaching the original native tool goal type with no observed tool errors; **the original CostBench answer oracle is not updated to validate the changed user preference**. None of the strict completions is verified end-to-end semantic success for a changed preference. Thus these are conservative execution diagnostics, not a genuine native benchmark leaderboard.

## Engineering diagnosis
- **EDR prompt alone** can make the model choose an updated preference action, but cannot enforce that following actions have valid inputs.
- **Action-level guard** can enforce stale evidence rejection and prevent prerequisite violations, but can cause non-completion when model correction or remaining action budget is insufficient.
- **Both tie a simple explicit fact-delta baseline on first action and strict completion in the current four-task cohort.**
- CostBench's unchanged semantic evaluator cannot certify the updated user's final task completion, so improvement claims remain limited.

## Stop decision
**STOP tuning on these four tasks. NO-GO to label EDR or this guard a successful new selective replanning algorithm, or a meaningful benchmark improvement.**

The next legitimate gate is a **fresh, preregistered set of independent actual agent-authored dynamic tasks** with a mutable factual state and a post-update goal verifier, and three fixed comparisons: minimal prompt, explicit temporal fact delta, bounded action guard. Measure false RETAIN, false SWITCH, valid tool actions, true updated-task completion, intervention counts, token usage and provider failures.

Until a candidate has a convincing real execution benefit over the extremely simple explicit temporal update baseline, do not advance to full algorithm release or CV claim of effectiveness.

## Exact reproducible sources
- [EDR method](evidence_dependency_refresh.py)
- [EDR native pilot runner](native_edr_policy_pilot.py)
- [EDR original outcomes](evidence/NATIVE_EDR_POLICY.json)
- [EDR independent audit](evidence/EDR_NATIVE_AUDIT.json)
- [Bounded action validator](action_evidence_guard.py)
- [Native action guard runner](native_action_guard_pilot.py)
- [Native action guard original outcomes](evidence/NATIVE_ACTION_GUARD.json)
- [Independent guard audit](evidence/NATIVE_ACTION_GUARD_AUDIT.json)
