# Study Protocol — Unified 50-Task RETAIN/SWITCH Benchmark

## Research question

When relevant environment facts change at a controlled CostBench checkpoint, does the Agent retain a still-valid continuation or switch to a better feasible continuation?

## Dataset and unit of analysis

The canonical benchmark contains **50 independent CostBench base tasks**. Each task contributes one matched RETAIN condition and one matched SWITCH condition from the same frozen checkpoint, yielding 100 condition records. The five task categories each contribute ten tasks.

The independent unit is the base task, not an individual condition, model request, tool call or trajectory.

## Paired condition construction

- RETAIN: the incumbent suffix remains optimal under the updated tool graph.
- SWITCH: a strictly better feasible suffix exists under the updated tool graph.
- Both conditions share the same checkpoint and differ in the controlled environment update.
- Labels are checked against the pinned CostBench solver and an independent graph calculation.
- Frozen inputs and hashes are stored under `experiments/paired_50/generated/`.

## Evaluation protocols

### Structured decision evaluation

DeepSeek Flash receives a frozen structured request and returns RETAIN or SWITCH. The saved results are 48/50 RETAIN correct, 3/50 SWITCH correct, and 1/50 fully correct matched pair.

### Native tool execution

The same 50 base tasks are evaluated through the pinned native CostBench harness. The archived native execution report records first-action adherence to the incumbent and goal completion. In 48/50 trials in each condition, the first action followed the incumbent; all 100 trajectories reached the goal. These are descriptive behavior measures, not a validated path-optimality score.

The two protocols measure different outcomes and are reported separately. The native protocol does not yet report validated path-level optimality. A different first action alone is not sufficient evidence of a correct SWITCH.

## Environment and reproducibility

Pinned CostBench revision: `6424069f3f773ade076bcedbed302ed47cfb1837`.

Run offline dataset verification:

```bash
python experiments/paired_50/build_unified_dataset.py --check
python -m unittest scripts.test_unified_paired_dataset scripts.test_source_fixture_integrity -v
```

Native execution protocol and results are documented under `experiments/paired_50/native_execution/`. Offline validation makes no paid model calls.

## Validity boundaries

The incumbent suffix is solver-derived and supplied at a controlled checkpoint. The study evaluates checkpoint decisions and observable actions relative to that incumbent; it does not establish autonomous plan authorship or a causal plan-commitment effect. Goal completion is reported separately from first-action adaptation.

See [canonical benchmark](../experiments/paired_50/README.md), [reproducibility](REPRODUCIBILITY.md), and [limitations](LIMITATIONS.md).
