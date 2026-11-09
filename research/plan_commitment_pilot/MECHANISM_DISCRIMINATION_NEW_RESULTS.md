# Mechanism discrimination of historical false-RETAIN behavior — new paid-model results

**Completed two newly executed development-stage trials.** Original 45 source tasks were not replaced, and the 3 old post-hoc probes remain excluded.

## Scope and provenance

- Earlier historical source: 30 independent tasks under protocol A (26/30 true-SWITCH false RETAIN) plus 15 disjoint tasks under protocol B (15/15 false RETAIN). 41/45 is a *descriptive combination of two protocols*, not one homogeneous error-rate estimate.
- New mechanism sample: five merged source archive tasks **not selected in the earlier ten-task mechanism diagnostic**: `Query00312`, `Query00347`, `Query00610`, `Query00685`, `Query00916`.
- New first run: [GitHub Actions #42445875910](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42445875910). 23 successful **new** DeepSeek Flash calls, 26,023 reported tokens. Planned maximum 25; **one of the five candidate generators returned an invalid candidate**, so the two matched candidate-conditioned decision arms for that task were intentionally not executed. Therefore the score artifact's `partial` status is accurate, not a system failure.
- Independent correction of misleading global-label scoring: [Actions #42445987666](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42445987666).
- New candidate identity control on four valid candidate tasks: [Actions #42446079621](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42446079621), 16 successful **new** DeepSeek calls, 19,975 reported tokens.
- **Total new experiments: 39 paid calls across five distinct previously studied development base tasks**, 45,998 provider-reported tokens. The four identity-control tasks **reuse** four of the first five. Not 39 independent tasks, not independent validation, and not native Agent execution.

## Stage 1 — generate an alternative without price or label cues

One generator response per task, graph dependencies and goal visible but numerical price values hidden. It was instructed to produce a **distinct type-feasible goal-reaching** alternative, not the best-price suffix. The same candidate, if valid, was held fixed across matched RETAIN and SWITCH conditions.

- **4/5** proposed routes passed independent type and goal checks; **1/5** failed prerequisites.
- The four valid routes were **not better than the supplied old path in either matched condition**. A globally better alternative may exist in a true SWITCH condition, but the generated candidate is not necessarily that alternative.
- Therefore the correct choice if instructed to compare **only old vs generated candidate** is RETAIN for all eight condition/route comparisons. It would be an error to score an answer SWITCH as correct merely because the original *global* task has label SWITCH.

## Stage 2 — original decision versus generated different candidate

Fresh original label-only control (10 judgments across 5 tasks): RETAIN 5/5; SWITCH 0/5, i.e. the old one-label phenomenon replicated on this new five-task development subset.

Generated-feasible-but-not-better candidate comparison (8 judgments across 4 tasks):
- Model output **SWITCH in 8/8**, yet the correct **two-option decision is RETAIN in 8/8**.
- **0/8** correct two-option actions.
- Model correctly reported the new candidate's value in **8/8**, but the old path's value in **0/8**.
- **6/8** of those SWITCH labels contradicted even the model's *own* reported pair of values. In the other two, the reported old value was wrongly inflated and the proposed SWITCH was consistent with those mistaken numbers.
- This is a new failure pattern: a prompt including a distinct feasible alternative can flip an all-RETAIN control into all-SWITCH without supplying a truly improving alternative.
- Since the prompt also changed from a single-label instruction to an explicitly scaffolded two-option instruction, this first run alone cannot isolate *candidate identity*.

## Stage 3 — match prompt and graph, change only candidate identity

Four base tasks × RETAIN/SWITCH environment × old-identical/new-different candidate = **16 new real DeepSeek calls**. Same source graph and condition, same response format and comparator instruction within each pair; **only candidate path identity changes**. Every presented candidate was feasible but never preferable to the incumbent, so **the correct two-option label is RETAIN for all 16** even if the original task's global label is SWITCH.

| Candidate identity | Correct RETAIN out of 8 | Incorrect SWITCH out of 8 | Correct old sum | Correct candidate sum | Output contradicts own reported numbers |
|---|---:|---:|---:|---:|---:|
| Same path as incumbent | **8** | 0 | 4/8 | 4/8 | 0/8 |
| Different, feasible but worse path | **3** | **5** | **1/8** | **8/8** | **2/8** |

Two findings are more precise than the original undifferentiated false-RETAIN claim:
1. **Novel candidate path identity is associated with switching behavior independent of whether the candidate improves the plan**, in a matched-prompt observation on four development tasks. The absolute switch rate changed from 0/8 identical-candidate to 5/8 different-but-worse candidate.
2. **Poor current incumbent evaluation and evidence-to-label inconsistency** contribute observable wrong decisions. In the distinct-candidate condition, the model gave a correct old sum only 1/8 times while correctly summing the proposed candidate 8/8 times. Two SWITCH labels directly contradicted its own reported figures.

These results are about **observable response construction and arithmetic consistency**, not model psychology. They do not prove a hidden commitment bias, self-serving agency, or that candidate novelty alone is a general population-level cause. Prompt format and model-session effects, small sample and handoff bias remain limitations.

## What this tells us about 41/45 historical false RETAIN

- Original 90 model responses are only one-field intervention labels, so **individual causes for those 41 errors remain unidentifiable** from the original completions. Verified original source: [historical audit](../../experiments/paired_50/README.md).
- Earlier 10-task diagnostics showed two distinct behavioral breakdowns: inability to produce an improving alternative, and action labels inconsistent with self-reported evidence.
- The new five-task study reproduces all-RETAIN behavior in original prompt, but new candidate-oriented prompts switch strongly even to worse plans. Thus a generic claim that the Agent *always clings to its old plan* is untenable as a mechanism explanation.
- A supported **narrower research hypothesis** is *unstable evidence-conditioned plan revision*: for the same plan and current facts, the model may over-retain when alternative evidence is not surfaced and over-switch when a different feasible candidate is presented, sometimes contradicting the available evidence. Test this prospective hypothesis in **native Agent continuation**, with truly self-authored plans, actual action choices, explicit competing factual observations, and correct post-update outcome evaluation.

## GO/NO-GO

**GO for further diagnosis** of whether different-vs-identical feasible candidate presentations and evidence contradictions affect **actual next tool actions** in independently sampled native-agent cases. Pre-register both RETAIN and SWITCH with valid action alternatives and no oracle-supplied best route.

**NO-GO for a new algorithm right now**, for treating 5 development tasks as heldout, for saying the new prompt increased true global SWITCH correctness, and for declaring an independently established plan-commitment effect.

Exact raw files:
- [First run frozen lock and trial evidence](evidence/mechanism_probe/LOCK.json)
- [First run detailed corrected score](evidence/mechanism_probe/SCORE.json)
- [Identity control lock](evidence/candidate_identity/LOCK.json)
- [Identity control detailed score](evidence/candidate_identity/SCORE.json)
