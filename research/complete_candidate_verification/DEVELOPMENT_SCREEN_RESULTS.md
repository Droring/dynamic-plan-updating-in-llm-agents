# Frozen 32-Trajectory Development Screen — Results

**Status: COMPLETE. Stop before the independent pilot.**

## Frozen protocol

- Cohort: 8 previously explored development tasks; not held out.
- Conditions: RETAIN and SWITCH for each base task.
- Methods: `repair_plus_fresh` and `fresh_plus_fresh`.
- Total: 8 × 2 × 2 = 32 native trajectories.
- Model: DeepSeek Flash, temperature 0, thinking disabled.
- Maximum planning calls: 3 per trajectory; the run used 2 per trajectory.
- Pinned CostBench revision: `6424069f3f773ade076bcedbed302ed47cfb1837`.
- Analysis unit: base task. The two methods are paired on each task-condition cell.

The cohort was outcome-enriched for method development. These results are not a held-out estimate and do not support a generalization claim.

## Execution integrity

| Check | Result |
|---|---:|
| Completed native trajectories | 32/32 |
| Unique task-condition-method cells | 32/32 |
| Goal reached | 32/32 |
| Selected plan exactly executed | 32/32 |
| Candidate paths valid, feasible and complete | 64/64 |
| Native tool calls returned successfully with output IDs | 60/60 |
| Provider requests received responses | 124/124 |
| Provider retries | 0 |
| Actual provider tokens | 408,466 / 1,200,000 |

Token accounting: 64 planning calls used 288,294 tokens; 60 argument-generation calls used 120,172 tokens. No provider or native outcome was uncertain.

## Primary and secondary results

| Method | RETAIN | SWITCH | Execution-grounded BA | Decision BA | Pair Accuracy | Goal success | Exact optimal trajectory |
|---|---:|---:|---:|---:|---:|---:|---:|
| Repair + Fresh | 8/8 | 4/8 | 75.0% | 75.0% | 50.0% | 100% | 62.5% |
| Fresh + Fresh | 8/8 | 4/8 | 75.0% | 75.0% | 50.0% | 100% | 62.5% |
| Difference | 0 pp | 0 pp | 0 pp | 0 pp | 0 pp | 0 pp | 0 pp |

Both methods produced the same selected plan and the same executed path in all 16 matched task-condition comparisons. The proposed Repair + Fresh method therefore showed no decision-level or execution-level improvement over the frozen Fresh + Fresh baseline.

Per-task outcome (identical for both methods):

| Base task | RETAIN | SWITCH |
|---|---|---|
| Query00178 | Correct | Incorrect |
| Query00351 | Correct | Incorrect |
| Query00440 | Correct | Correct |
| Query00549 | Correct | Incorrect |
| Query00598 | Correct | Correct |
| Query00662 | Correct | Correct |
| Query00689 | Correct | Incorrect |
| Query00851 | Correct | Correct |

The numerical development gates were met exactly at their minimum: RETAIN 8/8, SWITCH 4/8, BA 75%, and no degradation relative to the simple baseline. However, the plan also specified that no difference from the simple candidate baseline means simplify rather than expand. That stop rule applies here.

## Candidate-generation diagnosis

All 64 submitted candidates passed the path checker: each was valid, feasible and complete. All 32 trajectories reached the goal, and the executor followed the selected committed path. The four SWITCH errors were therefore not checker or native-execution failures.

The failures were candidate-coverage failures. In the four missed SWITCH tasks—Query00178, Query00351, Query00549 and Query00689—neither candidate source produced a feasible complete path strictly better than the incumbent. The strict selector consequently retained the incumbent, as specified.

Among the eight SWITCH conditions:
- The Repair candidate was strictly better than the incumbent in 3/8 tasks.
- The Fresh candidate was strictly better in 4/8 tasks.
- The union of the two sources covered 4/8 tasks.
- Repair added no SWITCH task with a strict-better candidate that Fresh had missed.

Repair + Fresh did increase candidate-path diversity: its two proposals differed in 9/16 trajectories, compared with 1/16 for Fresh + Fresh. But this diversity did not translate into an additional strict-better SWITCH candidate or a different selected plan.

## Baseline implementation caveat

The two Fresh calls in the frozen Fresh + Fresh baseline used identical prompt messages at temperature 0. They were separate provider requests, but not independent stochastic samples. Their candidate paths were identical in 15/16 trajectories. This is an important limitation of the baseline as implemented; do not describe those calls as independent samples.

This caveat does not change the observed result: under the frozen comparison, Repair + Fresh did not improve BA, SWITCH coverage, Pair Accuracy or executed plans. It does limit how broadly the baseline comparison can be interpreted.

## Decision under the pre-registered stop rule

**Do not proceed to the 12-task independent pilot with this version.**

The current method has not demonstrated incremental value over the simple candidate baseline. Per the frozen plan, stop expansion and simplify the method before considering another experiment. No additional API calls or task additions are authorized by this result.

The supported conclusion is narrow: the submitted-path checker and committed-plan executor operated reliably on this development cohort, while the proposed repair candidate did not add SWITCH coverage beyond fresh replanning. This is a development finding, not evidence of held-out performance.

## Reproducibility

- GitHub Actions run: [43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958)
- Workflow artifact: `complete-candidate-development-screen` (artifact ID `13868243944`)
- Artifact SHA-256: `d5b71f94985c8c7d19bff1a37daf3403af7121989e608295842df3255b4b64bf`
- Response log SHA-256: `e4bc402694dcdc2eff25b4a968ce1ce7528a5a2a640502756674fdbb540555e0`
- Provider event log SHA-256: `f1bd602039764af7e1a7f879a5bd2785b5e1f3f6f2dacaffffa57050b1fa14ea`
- Native event log SHA-256: `5c090bc704c6028909012beacd8fd28192269f15fccab994484b42d19c51a9a7`
- Experiment code commit: `a6fc8d623f7dba0b90a4d9601f199dec17b037b3`
