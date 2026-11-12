# Independent Validation Task Selection

**Status: 20 base tasks selected and overlap-audited; no model or native trajectories have been executed.**

## Source and selection

The cohort is selected from the pre-allocated 40-task Validation split in the CostBench 200-task allocation (80 Development / 40 Validation / 80 locked Test). It uses the pinned upstream CostBench revision and the existing allocation seed. Four tasks are selected per each of the five CostBench categories by taking the first four records in each category's frozen Validation registry order. No task outcomes, ground-truth paths, or answer keys were used.

| Category | Selected task IDs |
|---|---|
| Transportation | Query00199, Query00247, Query00187, Query00203 |
| Accommodation | Query00349, Query00408, Query00443, Query00350 |
| Attraction | Query00603, Query00637, Query00555, Query00585 |
| Dining | Query00749, Query00725, Query00747, Query00715 |
| Shopping | Query00959, Query00942, Query00892, Query00910 |

The other 20 tasks in the 40-task Validation pool remain unused.

## Independence checks

The 20 selected tasks have zero query-ID overlap with the 50-task paired RETAIN/SWITCH cohort, the 80-task official CostBench development cohort, the eight-task complete-candidate development screen, and the eight-task four-arm prompt screen. The 67-event native checkpoint cohort is a subset of the 80-task official development cohort; it adds no separate task IDs.

All 20 selected query IDs, source-query hashes, and preference hashes are unique. The detailed machine-readable manifest records each source hash and exact registry position. The automated manifest test rechecks these conditions against the source registries.

## Planned experiment

The selected 20 tasks are paired under RETAIN and SWITCH and compared across seven methods, giving 280 planned native trajectories. The seven methods and go/no-go criteria are recorded in the manifest and in [LOCAL_SUBSTITUTION_MECHANISM.md](LOCAL_SUBSTITUTION_MECHANISM.md).

## Remaining freeze items

Task membership is selected, but the experiment is not ready for paid execution. Before any provider calls:
1. Freeze the checkpoint-construction procedure and confirm whether the incumbent suffix is agent-authored or solver-derived. All seven arms must start from the same checkpoint and information state.
2. Pin the exact implementation/configuration of the existing bounded-verifier arm and the full-graph planner.
3. Freeze the total token ceiling, output-token cap, retry policy, and artifact/log schema.
4. Run the complete offline preflight and verify the 280-cell schedule.

No paid DeepSeek calls, native trajectories, or final-test runs have been started. The 80-task locked-test pool remains untouched and no final-test IDs are selected.
