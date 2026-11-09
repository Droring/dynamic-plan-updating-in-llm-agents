# Claim–Evidence Matrix

This matrix maps current paper-facing claims to their canonical evidence. Independent base tasks, matched conditions, trajectories and event checkpoints are reported separately.

| Claim | Canonical evidence | Result | Scope |
|---|---|---:|---|
| The paired RETAIN/SWITCH benchmark is balanced and reproducible | [50-task registry and build report](../experiments/paired_50/README.md); [offline integrity tests](../scripts/test_unified_paired_dataset.py) | 50 independent base tasks; 100 matched conditions; 10 tasks per category | Solver-derived checkpoints and incumbent suffixes |
| DeepSeek Flash shows asymmetric structured RETAIN/SWITCH decisions | [Saved structured scores](../experiments/paired_50/live_results/deepseek-flash/scores.json) | RETAIN 48/50; SWITCH 3/50; pair 1/50; balanced accuracy 51% | Controlled structured decision protocol |
| The same paired task set shows weak first-action adaptation in native execution | [Native execution results](../experiments/paired_50/native_execution/RESULTS.md) | RETAIN 48/50; SWITCH 2/50; paired 1/50; same decision in 48/50 pairs; goal reached 100/100 | Observable first native tool action; solver-derived incumbent |
| Dynamic execution is less robust than static execution in the official Agent | [Official 80-task audit](../experiments/native_80/README.md) | Static 70/80; dynamic 60/80; 13 correct-to-incorrect; 3 incorrect-to-correct | Archived official CostBench final-answer outcomes |
| Native plan-commitment and evidence-gate conditions can be audited | [Plan-commitment/evidence-gate study](../research/costbench_method_studies/plan_commitment_evidence_gate/README.md) | 67 replay-matched event checkpoints; 27 authentic prospective plans parsed | Separate audit; not part of the 50-task denominator |
| EDR and Action Guard have not demonstrated improvement over a simple fact update | [Intervention report](../research/plan_commitment_pilot/FIRST_METHOD_ITERATION.md) | No demonstrated end-to-end advantage in four-task development pilot | Exploratory, reused development tasks |

## Claim boundaries

- The structured decision protocol and native first-action protocol are different outcome measures; do not combine their accuracies.
- The 50 tasks are the independent units. The 100 condition records and 100 native trajectories are paired observations.
- The supplied incumbent suffix is solver-derived; do not describe it as an Agent-authored plan.
- Goal completion does not establish correct RETAIN/SWITCH adaptation.
- The official 80-task robustness audit, 67-checkpoint plan-commitment audit and four-task intervention pilot are separate evidence packages.
- Current evidence does not validate a new algorithm or establish that all dynamic failures are caused by plan commitment.

For interpretation and reproduction, see [limitations](LIMITATIONS.md), [reproducibility](REPRODUCIBILITY.md) and the [research mainline](../research/plan_commitment_pilot/RESEARCH_MAINLINE.md).
