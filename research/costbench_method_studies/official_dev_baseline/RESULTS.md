# Official Native Dynamic-Robustness Study: CostBench Agent Baseline (80 Development Tasks)

## Executive summary

DeepSeek Flash was evaluated using the pinned, unmodified CostBench Agent loop on **80 independent development tasks**, with one static and one official cost-change run per task. These are **160 correlated trajectories**, not independent task samples. The validation (40) and locked-test (80) tasks were not evaluated.

Official final-answer accuracy was **70/80 (87.5%) static** and **60/80 (75.0%) dynamic**. The observed paired difference (dynamic minus static) was **-12.5 percentage points** (task-resampled descriptive 95% bootstrap interval [-21.2, -3.8] points). Exact two-sided McNemar p = **0.02127**. This is exploratory analysis on a development set; it does not establish method improvement or a causal price-change effect.

Crucially, the dynamic event was actually triggered in **67/80** tasks. The other **13/80** ended before the planned event, including early stops that the upstream runner recorded as completed. These cases must **not** be interpreted as unsuccessful recovery after observing a price change.

## Full-denominator outcome table

| Metric | Static | Official cost change |
|---|---:|---:|
| Attempted task-condition trajectories | 80 | 80 |
| At least one native tool called | 80/80 (100.0%) | 68/80 (85.0%) |
| Goal type reached | 80/80 (100.0%) | 66/80 (82.5%) |
| Official final answer accepted | 70/80 (87.5%) | 60/80 (75.0%) |
| Official evaluation present | 80/80 (100.0%) | 80/80 (100.0%) |
| No native tool called | 0/80 (0.0%) | 12/80 (15.0%) |
| Official cost-change event triggered | N/A | 67/80 (83.8%) |

## Matched-task outcomes

| Both correct | Static only | Dynamic only | Neither correct |
|---:|---:|---:|---:|
| 57 | 13 | 3 | 7 |

Among the **67** dynamic trajectories where a cost-change event actually fired, **60/67** dynamic answers were accepted. Static results on those same task IDs were **58/67**. This conditional subset is **selected based on dynamic execution**, so it is diagnostic only and cannot replace the full 80-task estimate.

## Early termination before a dynamic event

The event was not observed in the following run types:

| Audited early-stop type | Count |
|---|---:|
| assistant without tool or final answer | 2 |
| no assistant message recorded | 10 |
| tool prefix stopped before event | 1 |

The upstream runner can label a case completed even when the required goal state was never reached. Some histories contain no assistant message at all; the archived files do not preserve enough provider-side error information to distinguish transient request failure from other causes. Treat them as **incomplete Agent trajectories with an unknown underlying cause**, not proven replanning failures.

## Category-stratified results

| Category | Distinct tasks | Static correct | Dynamic correct |
|---|---:|---:|---:|
| accommodation | 11 | 10/11 (90.9%) | 10/11 (90.9%) |
| attraction | 12 | 10/12 (83.3%) | 9/12 (75.0%) |
| dining | 15 | 15/15 (100.0%) | 11/15 (73.3%) |
| shopping | 18 | 14/18 (77.8%) | 8/18 (44.4%) |
| transportation | 24 | 21/24 (87.5%) | 22/24 (91.7%) |

## Resources and cost accounting

| Official aggregate | Static | Cost change |
|---|---:|---:|
| Valid CostBench queries used by official cost aggregation | 80 | 67 |
| Native tool calls in official score aggregates | 213 | 186 |
| Simulated Agent tool-cost sum (official units) | 7995.37 | 6555.29 |
| Simulated reference cost sum (official units) | 7995.37 | 6548.25 |
| Provider tokens, API dollars, per-task latency | not recorded | not recorded |

The official aggregate-cost denominators **differ** (80 vs 67); totals are therefore not a fair per-task treatment comparison. GT and Agent costs may also be evaluated from different execution states. No aligned-state regret, token savings, API spend or replanning latency improvement is inferred.

## Failure inventory (all task-condition failures retained)

Each entry represents a task-condition trajectory, not an independent experiment.

| Task | Condition | Goal reached | Final accepted | Native calls | Event triggered | Diagnostic |
|---|---|---|---|---:|---:|---|
| Query00263 | official_cost_change | True | False | 3 | 1 | final_answer_not_accepted |
| Query00263 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00292 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00310 | official_cost_change | True | False | 3 | 1 | final_answer_not_accepted |
| Query00310 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00452 | official_cost_change | True | False | 4 | 1 | final_answer_not_accepted |
| Query00452 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00532 | official_cost_change | True | False | 2 | 1 | final_answer_not_accepted |
| Query00532 | static | True | False | 2 | 0 | final_answer_not_accepted |
| Query00538 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00562 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00597 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00687 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00764 | official_cost_change | False | False | 1 | 0 | tool_prefix_stopped_before_event |
| Query00770 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00791 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00835 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00843 | official_cost_change | True | False | 2 | 1 | final_answer_not_accepted |
| Query00843 | static | True | False | 2 | 0 | final_answer_not_accepted |
| Query00849 | official_cost_change | False | False | 0 | 0 | assistant_without_tool_or_final_answer |
| Query00853 | official_cost_change | False | False | 3 | 1 | goal_not_reached |
| Query00857 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00896 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00901 | official_cost_change | False | False | 0 | 0 | assistant_without_tool_or_final_answer |
| Query00901 | static | True | False | 2 | 0 | final_answer_not_accepted |
| Query00913 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00963 | official_cost_change | False | False | 0 | 0 | no_assistant_message_recorded |
| Query00986 | official_cost_change | True | False | 3 | 1 | final_answer_not_accepted |
| Query00986 | static | True | False | 3 | 0 | final_answer_not_accepted |
| Query00991 | static | True | False | 3 | 0 | final_answer_not_accepted |

## Research interpretation and limits

1. This is a **baseline for the official CostBench reactive Agent**, not a verification/local-repair controller evaluation. A changed execution path alone does not establish that an LLM internally decided to replan.
2. The early-stop concentration in non-triggered dynamic runs requires dedicated instrumentation and technical diagnosis before making claims about robustness to *observed* cost changes.
3. Official dynamic cost changes are not the same as the seven graph-only constructed event families. Ground-truth cost comparisons require explicit aligned-state checks before interpreting regret.
4. The tasks were development candidates that had already passed graph feasibility screening; this is not a blind test of a newly proposed method.
5. A simple task-clustered bootstrap reflects uncertainty from task-level variability but cannot correct bias in how CostBench cases were selected or guarantee generalization to production environments.

## Provenance and reproduction

- [Frozen task, model, and version manifest](evidence/inputs/manifest.json)
- [Complete deterministic task and category audit](evidence/SUMMARY.json)
- [Eight original official CostBench output files](evidence/results/)
- [Official native execution protocol](README.md)

To reproduce the report from the saved audit: python research/costbench_method_studies/official_dev_baseline/render_report.py --summary research/costbench_method_studies/official_dev_baseline/evidence/SUMMARY.json --out /tmp/official_native_results.md
