# Unified RETAIN/SWITCH Decision and Native Execution Study

<badge color="success">Canonical paired benchmark</badge>

**Dataset:** 50 independent CostBench base tasks, 100 matched conditions (50 RETAIN, 50 SWITCH), balanced across five task categories.

## Dataset

Every base task has one RETAIN condition and one SWITCH condition derived from the same frozen checkpoint. The five CostBench categories contribute ten tasks each. The canonical registry, pair fixtures, frozen requests and trial manifest are stored in `generated/`.

The first 45 task pairs are merged in `provenance/source_records/source_archive/source_pairs.json`; five new tasks complete the 50-task registry. Raw source materials and historical evaluation records remain nested in that archive for traceability. They are not separate current experiments.

## Results

### Structured decision evaluation

DeepSeek Flash completed all 100 judgments:

| Measure | Result |
|---|---:|
| RETAIN accuracy | 48/50 (96%) |
| SWITCH accuracy | 3/50 (6%) |
| Paired accuracy | 1/50 (2%) |
| Balanced accuracy | 51% |

### Native CostBench execution

The same 50 base tasks completed 100 native tool-execution trajectories using the pinned upstream CostBench implementation:

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | 48/50 (96%) |
| SWITCH first-action accuracy | 2/50 (4%) |
| Overall first-action accuracy | 50% |
| Paired first-action accuracy | 1/50 (2%) |
| Same first-action decision in both conditions | 48/50 (96%) |
| Goal reached | 100/100 |

The structured protocol measures an explicit decision label; native execution measures the first executed tool relative to the incumbent suffix. These are separate outcomes. The agent reached every goal, but its first action rarely changed with the paired environment condition. See [native execution protocol](native_execution/README.md) and [detailed results](native_execution/RESULTS.md). The [mechanism analysis](native_execution/MECHANISM_ANALYSIS.md) stratifies SWITCH failures by the location of the changed tool value and paired first-action consistency.

## Reproduction

Use Python 3.12 and the pinned CostBench revision `6424069f3f773ade076bcedbed302ed47cfb1837`.

- Verify the dataset: `python experiments/paired_50/build_unified_dataset.py --check`
- Verify saved structured results: `python -m unittest scripts.test_unified_paired_dataset -v`
- Verify source-fixture disjointness: `python -m unittest scripts.test_source_fixture_integrity -v`
- Verify native protocol: follow [native execution instructions](native_execution/README.md)

The frozen request and manifest hashes are recorded in the result artifacts. Offline checks make no model API calls. Re-running paid model evaluation requires explicit live execution and provider credentials.

## Interpretation

The 50 independent base tasks are the unit of analysis. The 100 conditions and native trajectories are paired observations, not additional independent tasks. The incumbent suffix is solver-derived and supplied at a controlled checkpoint. The study measures checkpoint decisions and observable execution relative to that incumbent; it does not claim that the Agent independently authored the original plan.
