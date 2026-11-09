# Complementary CostBench Native Studies

This directory contains the native CostBench evidence packages that complement the primary [50-task paired benchmark](../../experiments/paired_50/README.md).

## Current evidence packages

- [Official Native Dynamic-Robustness Study](official_dev_baseline/RESULTS.md): 80 tasks, with static and dynamic outcomes from the official Agent; one task is shared with the primary 50-task cohort.
- [Native Plan-Commitment and Evidence-Gate Study](plan_commitment_evidence_gate/README.md): 67 replay-verified event checkpoints from the same 80-task development population, including the audit of authentic prospective Agent-authored plans.
- [Official native task allocation](official_native_task_allocation/README.md): the documented 200-candidate source population and 80/40/80 allocation used by the official native study. This is a registry, not 200 completed Agent evaluations.

The plan-commitment runtime contains the shared graph and replay utilities needed to reproduce its own evidence. Superseded prompt-only, controller-comparison and bounded-search prototypes are not part of the current experiment index.

## Statistical units

The 80-task official baseline and 67-event plan-commitment audit are related but distinct measurements. The 67 checkpoints are a subset selected by an observed event; they are not 67 additional tasks. Neither denominator is added to the primary 50-task benchmark.
