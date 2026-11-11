# Plan-Preserving Evidence Comparison: Development Experiment

## Objective

Improve **balanced first-action correctness** across RETAIN and SWITCH under environment changes, without removing the incumbent plan. This is a *candidate method pilot*, not yet a validated replanning algorithm.

The prior formal screen used eight reused base tasks, two conditions and two repetitions. Under the incumbent-visible A baseline, first-action correctness was RETAIN 16/16 and SWITCH 2/16, balanced accuracy **56.25%**. Removing the plan (C/D) improved SWITCH but degraded RETAIN and did not improve balanced accuracy.

Subsequent candidate diagnostics on the same eight tasks (seven first-action SWITCH failures, plus RETAIN checkpoints) found an optimal non-incumbent action reported in 6/7 SWITCH cases, but only 6/14 correct decisions with a supplied oracle-quality candidate menu. The method should therefore preserve the incumbent as context while prompting explicit comparison of feasible continuations.

## Interventions

Implementation: [`run_balanced_replanning.py`](run_balanced_replanning.py), sharing the frozen native CostBench evaluator and task manifest.

Both methods preserve **the entire original A prompt**, including the plan cue and current tool interfaces:

- **comparison:** Explicitly instruct the model to compare alternative feasible remaining continuations under *current* tool facts, retaining the incumbent unless a strictly better path is supported. This is a prompt-only structured-decision baseline.
- **feasible_menu:** The same instruction plus an alphabetical list of **all currently type-feasible native tool names** computed only from the checkpoint's visible interface and available typed state. The list contains no oracle scores, optimality labels, recommendation order or solver-derived candidate rankings. It can contain irrelevant tools.

The method prompts contain no oracle path, gold label, minimal-value reference or recommended first action. The native solver is used **only after generation** to score chosen actions. The added instructions do not by themselves establish a novel algorithm: efficacy must be demonstrated in the original environment.

## Frozen design and outcomes

- **Development population:** eight base tasks already used in mechanism diagnosis. This is **not held-out testing**.
- **Conditions:** 8 RETAIN + 8 SWITCH checkpoints, 2 methods, 2 repetitions = **64 new DeepSeek first-action trials**.
- **Model:** DeepSeek Flash, temperature 0, thinking disabled.
- **CostBench revision:** `6424069f3f773ade076bcedbed302ed47cfb1837`, native types, tools and action executor.
- **Original baseline:** A-arm 128-request formal archive, using its 16 RETAIN and 16 SWITCH first actions for the same eight tasks and two repetitions. Do not recount existing samples as new.
- **Primary endpoint:** first-action optimality separately by RETAIN and SWITCH, plus balanced accuracy = (RETAIN accuracy + SWITCH accuracy)/2. Report per-base-task paired observations before aggregate.
- **Secondary:** incumbent-following counts, first-action action regrets as a diagnostic, invalid calls, goal-execution status for any follow-up.
- **Query00403:** SWITCH at full-path level, yet incumbent first action remains optimal. It counts as first-action-optimal if chosen but **does not prove a successful full-path switch**. Never reinterpret first-action correctness as full-path path update.
- Two repeated calls on one base task are correlated, not independent samples.

### Decision rule

A method is a **promising development candidate** only if it has balanced accuracy **strictly above 56.25%**, RETAIN first-action correctness **at least 14/16 (87.5%)**, SWITCH correctness **at least 8/16 (50%)**, no invalid or infeasible native action, and a positive paired task-level benefit over baseline. Meeting this rule is *not* evidence of held-out generalization, just cause to advance to independent tasks and full-path continuation.

If neither method meets all conditions, report a negative pilot and retain the mechanism diagnosis; do not revise this cohort's thresholds afterward.

## Reproducibility and restrictions

The official native harness is pinned; model calls require `--live` and an API key. Dry runs make zero provider calls. The archived raw requests, responses, first native tool execution results, and token ledger are the primary reproducible evidence.

The new methods are evaluated only on previously observed pilot tasks. Any method tuning must use this development cohort and **reserve other paired-50 tasks for untouched confirmation**, followed by end-to-end paths before a method claim. No claims of plan anchoring as a psychological mechanism are made.

Offline check:

```bash
python experiments/paired_50/native_execution/run_balanced_replanning.py --costbench-root ../CostBench
```
