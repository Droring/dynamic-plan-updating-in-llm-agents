# Official Native Dynamic-Robustness Study

**Status:** completed audit of the official CostBench Agent on 80 independent development tasks.

## Scope and execution

Each task was evaluated in two conditions: static execution and an official dynamic environment update. This produced 160 paired trajectories, not 160 independent tasks. The 40 validation and 80 locked-test candidates were not evaluated. One development task (`Query00499`) also appears in the primary 50-task paired benchmark; report the two evidence packages separately and do not sum their task counts.

The full Agent execution loop is the unmodified official CostBench `env/run.py` at commit `6424069f3f773ade076bcedbed302ed47cfb1837`, using DeepSeek Flash, temperature 0, refinement level 2, the official tool creation seed, and the frozen execution configuration. The native tool environment and original prompt were retained.

## Main outcomes

Official final-answer accuracy was **70/80 static** and **60/80 dynamic**. There were 13 tasks that changed from static-correct to dynamic-incorrect and 3 in the opposite direction. The dynamic event was observed in 67/80 tasks; the remaining 13 ended before the event and are not counted as post-event recovery cases.

These results measure final-answer robustness. They do not identify the cause of every degraded trajectory or establish the effectiveness of a replanning intervention.

## Evidence and reproduction

The fixed task manifest, original native result shards, summary and audit code are stored under `evidence/`. The task population is defined by the [candidate registry allocation](../official_native_task_allocation/README.md).

Run the offline audit from the repository root:

```bash
python research/costbench_method_studies/official_dev_baseline/audit.py --root research/costbench_method_studies/official_dev_baseline/evidence --out /tmp/native80_verification.json
```

A fresh model evaluation requires explicit provider credentials and separate authorization. Offline reproduction does not invoke a model.
