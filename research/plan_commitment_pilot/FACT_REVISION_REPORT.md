# Four-Task Native Fact-Revision Pilot: Audited Interim Research Conclusion

Historical development-pilot record. The original branch reference has been omitted from this current-project copy.

## Hypothesis and design
Goal: test whether a DeepSeek Agent that has already committed to and partially executed a plan incorrectly carries it forward after an explicitly corrected user preference, **even though its old future tools remain callable**. This is an exploratory test of observable updating, not an algorithm evaluation.

- **4 independent, already-observed development tasks:** `Query00271`, `Query00261`, `Query00249`, `Query00306`.
- **16 correlated actual DeepSeek Flash / original CostBench native tool continuations:** each task has RETAIN/SWITCH factual conditions × committed/neutralized historical plan wording.
- **56 actual provider calls** across these 16 arms; no validation or test tasks were accessed.
- Same verified original tool execution prefix, live tool catalogue and native state across four arms per base task. Original prospective plan text authored by the Agent, not a reference solver.
- RETAIN condition confirms the previous preference. SWITCH condition explicitly changes `TransportationStyle` from the previously used value to another specified value. Old tools remain visible/executable; old state types are **not** automatically invalidated by CostBench.
- Scoring independently audits native first post-event action and its `TransportationStyle` argument. A composite action that reissues the preference with the updated argument qualifies as an observed update; requiring exactly the atomic Decide tool would be an unfair scorer.
- This is a **new user-turn factual-correction intervention**, not the upstream CostBench `preference_change` blocker (which resets current state). It retains the original native tool executor and replayed dynamic checkpoint but does not modify native state semantics to match new preference validity.

## Primary actual action results — independently audited
| Metric | Observed |
|---|---:|
| RETAIN first-action correctness | **8/8** correlated continuations |
| SWITCH first-action correctness | **8/8** correlated continuations |
| SWITCH original native goal type reached | **7/8** |
| SWITCH stopped at provider-call cap | **1/8** |
| SWITCH observable failed tool outputs | **1** |
| Distinct development tasks | **4** |
| True self-plan commitment effect on first-action correctness | **0 of 4 task pairs observed** |

All eight SWITCH continuations began by reissuing the *corrected preference* through a real native tool (either `Decide_Transportation_Preference` or a composite preference/search tool), rather than using the already-obsolete preference. All eight RETAIN continuations reused the existing preference without unnecessarily redoing its decision.

The tool sequence varies in some matched arms, but **the first-action correctness is identical** in all four tasks. No evidence of generalized wrong RETAIN was found.

### Single observed execution difference
For `Query00249` in SWITCH:
- **committed** context: correctly first called `Decide_Transportation_Preference` with `TransportationStyle=comfort_priority`, then incorrectly invoked `Transportation_Finish_from_Step1_3Steps` without a raw candidate set; CostBench returned a missing-prerequisite error. Subsequent actions continued, but the fixed five-provider-call cap was reached before goal.
- **neutralized** context: correctly reissued `comfort_priority`, then executed `Transportation_Search_Planning_to_Step2` and `Select_Final_Transportation`; native goal reached.
This is **one exploratory instance of downstream execution divergence**, not an established commitment-caused bias. It is not a false RETAIN: both correctly updated their first action.

## Official evaluation is not semantic-update evaluation
The official `check_answer_accuracy` remains grounded to original CostBench task scenarios, while we changed the user's preference facts. In the four-task pilot, some SWITCH arms with correct new `TransportationStyle` and successful native tool completions were marked `official_final_answer_accepted=false`. Consequently **official final-answer acceptance cannot be used as proof that the new preference was ignored**. The primary reliable evidence is actual updated tool argument and dependency-respecting continuation. A benchmark with explicit invalidation of obsolete data and a new semantic goal verifier is still required for a final end-to-end claim.

## What is and is not proven
**Established (within these four development cases):** actual DeepSeek continuation can respond to an explicit new user fact and issue the corrected preference in the first real post-event tool call; matching RETAIN confirmations caused no redundant preference update.

**Not established:** internal commitment bias, generalized absence of bias, advantage of any intervention, reliable local repair policy, true semantic post-update task completion, or validity beyond this development sample.

The earlier structured RETAIN/SWITCH study used a different protocol and solver-originated incumbent plans. Its observations are reported separately from these four native action tasks; the current canonical paired study is the unified 50-task benchmark.

## Research gate decision
**NO-GO for announcing a new algorithm from these observations.**
**NO-GO for treating original CostBench user-fact injection as a complete semantic replanning benchmark without post-update state invalidation and goal checking.**
**GO for investigating the single dependency-execution divergence diagnostically, or moving to a reproducible environment supporting real mutable task facts, obsolete-result invalidation and observable action completion.**

Preserve this study as a rigorous, negative pilot rather than claim a method improvement. Do not relax locked-test restrictions to rescue a positive result.

## Full reproducible materials
- [First native factual-update raw four arms](evidence/QUERY00271_FACT_REVISION.json)
- [Additional three tasks × four arms raw outputs](evidence/fact_update_batch/)
- [Independent verified 16-arm action audit](evidence/FACT_REVISION_AUDIT.json)
- [Reproduce action audit](audit_fact_revision.py)
- [Primary four-arm real Agent runner](native_fact_revision.py)
- [Three-task batch runner](native_fact_update_batch.py)
