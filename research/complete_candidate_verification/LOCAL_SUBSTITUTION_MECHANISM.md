# Bounded Type-Contract Local Substitution

**Status: implementation and offline validation PASS; independent evaluation NOT STARTED.**

## Motivation

The frozen 32-trajectory development screen produced four incorrect SWITCH decisions. All submitted candidates were complete and feasible, and the selected plans executed successfully. The selector retained the incumbent because neither historical candidate source supplied a strictly better complete path.

The Fresh prompt did not include the incumbent, so these four failures cannot be attributed solely to direct exposure to the old plan. The archived candidates instead show a candidate-coverage problem: the model often proposed a feasible path but missed a lower-value composition already expressible with the current tool catalogue.

## Retrospective development audit

The audit uses the archived first Fresh proposal from the fresh_plus_fresh development arm, the corresponding incumbent suffix, and the exact public tool contracts visible at each checkpoint. The current fresh_with_local_substitution operator is then run on the incumbent and Fresh paths. The oracle value is read only after selection to score the result; it is not included in PolicyInput.

| Query | Incumbent | Fresh candidate | Best local substitute | Selected value | Audited optimum | Source of optimum |
|---|---:|---:|---:|---:|---:|---|
| Query00178 | 77.35 | 77.65 | 76.05 | 76.05 | 76.05 | Local substitution |
| Query00351 | 58.66 | 59.08 | 57.36 | 57.36 | 57.36 | Local substitution |
| Query00440 | 61.51 | 60.21 | 60.26 | 60.21 | 60.21 | Fresh candidate |
| Query00549 | 79.09 | 79.13 | 77.79 | 77.79 | 77.79 | Local substitution |
| Query00598 | 62.55 | 61.37 | 61.25 | 61.25 | 61.25 | Local substitution |
| Query00662 | 62.01 | 60.71 | 60.73 | 60.71 | 60.71 | Fresh candidate |
| Query00689 | 78.99 | 79.41 | 77.69 | 77.69 | 77.69 | Local substitution |
| Query00851 | 84.04 | 82.92 | 82.74 | 82.74 | 82.74 | Local substitution |

Across the 16 RETAIN/SWITCH checkpoints:

- RETAIN: **8/8** retained the incumbent and matched the audited optimum.
- SWITCH: **8/8** selected a strictly better complete path and matched the audited optimum.
- The Fresh candidate already matched the audited optimum in **2/8** SWITCH tasks.
- Local substitution supplied an audited-optimal candidate in the remaining **6/8** SWITCH tasks.

This is a retrospective result on the same eight previously explored tasks used to diagnose and shape the operator. The fixed four-tool/two-tool search bounds were selected during development. The 16/16 result is therefore development evidence, not independent confirmation or a generalization estimate.

The compact fixture development_screen_local_substitution_fixture.zlib.b64 is derived from GitHub Actions run [43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958), artifact 13868243944 (SHA-256 d5b71f94985c8c7d19bff1a37daf3403af7121989e608295842df3255b4b64bf). It preserves the typed contracts and post-hoc scores needed to reproduce the audit without replaying provider requests.

## Method definition

The experimental strategy is fresh_with_local_substitution:

1. Reconstruct the current typed state and incumbent suffix from confirmed observations.
2. Make exactly one Fresh request for a complete candidate path. The incumbent is not exposed in this candidate prompt.
3. Use the incumbent and the syntactically complete Fresh proposal as the only search anchors.
4. For every contiguous anchor segment of at most four tools, record its starting state, cumulative value, and final output type.
5. Enumerate replacement sequences of at most two currently exposed tools. Each replacement tool must have all required input types available at that point. The replacement sequence must produce the original segment's boundary output type.
6. Splice each replacement into its anchor path and validate the entire resulting path using the unchanged submitted-path checker.
7. Pass the Fresh proposal and all validated local alternatives to the unchanged strict selector. Retain on ties; switch only to a strictly better complete path.
8. Commit and execute the exact selected path with the existing state-bound executor.

The checker remains verification-only. The local operator is a separate bounded candidate generator. It does not silently repair invalid Fresh paths, add arbitrary missing suffixes, or search from the checkpoint to the goal.

## Difference from full graph planning

The local operator is anchored to at most two supplied complete paths: the incumbent and one Fresh proposal. It substitutes a contiguous segment of at most four tools with a sequence of at most two tools that reaches the same typed boundary. It does not enumerate arbitrary paths from the checkpoint.

The full-graph comparator remains a separate method that searches the reachable typed state space from the checkpoint. Because CostBench exposes an explicit type/dependency graph and tool values, the local operator is a bounded symbolic planning procedure, not evidence that the LLM independently discovered the optimal route. The independent study must include full graph planning as a strong information-matched baseline.

## Information boundary and model-call budget

The operator reads only the current public tool contracts: required input types, output type, and current per-tool value. It does not read condition labels, answer keys, reference paths, oracle values, or evaluation scores. It makes no model calls. The complete method uses one Fresh planning request plus argument-generation calls for the committed path.

The search bounds are fixed at four replaced tools and two replacement tools. They are not to be tuned on the independent validation or final test cohorts.

## Limitations

- The current CostBench typed-state model is monotonic and each tool exposes one output type in its public description. State deletion, side effects, and argument-dependent output types are outside this implementation.
- A better path may require replacing more than four contiguous tools or using more than two replacement tools.
- The operator depends on public tool contracts and values being complete and current. A catalogue change invalidates the execution certificate.
- The retrospective cohort contains repeated tool patterns and was used to design the operator.
- The method is structurally a limited graph-search procedure; its value must be established against ordinary candidate generation and full graph planning, not inferred from its retrospective 16/16 score.

## Next independent validation

The agreed next validation uses **20 entirely new CostBench base tasks**, four from each of the five task categories. The cohort is selected from the pre-allocated 40-task Validation split; its manifest and overlap audit are documented in [INDEPENDENT_VALIDATION_TASK_SELECTION.md](INDEPENDENT_VALIDATION_TASK_SELECTION.md). It compares seven methods, for **20 × 2 conditions × 7 methods = 280 native trajectories**:

1. Original DeepSeek Agent.
2. Simple RETAIN rule.
3. Best existing prompt: frozen A_original arm from the prior four-arm screen; see [BEST_EXISTING_PROMPT_SELECTION.md](BEST_EXISTING_PROMPT_SELECTION.md).
4. Existing bounded verifier with complete-plan handoff.
5. Ordinary Fresh full-candidate generation with the same checker and executor.
6. **New method: fresh_with_local_substitution.**
7. Full graph planning with the same executor.

The original repair_plus_fresh method remains a historical development arm; it is not the new method because it added no unique SWITCH coverage in the 32-trajectory screen.

The model configuration is DeepSeek Flash, temperature 0, thinking disabled. The maximum is three planning calls per trajectory; parameter-generation calls are counted separately and included in total usage. The total token ceiling and maximum output settings must be frozen before any paid run. The checkpoint-construction procedure and exact implementations of all seven arms must also be pinned.

The hard validation gates are:

- RETAIN accuracy: **20/20**.
- SWITCH accuracy: **at least 14/20**.
- Balanced accuracy: **at least 85%**.
- The new method must not fall below the ordinary complete-candidate control.
- Goal success and complete-trajectory quality must not regress.

The later test remains sealed and unselected. The pre-allocated 80-task locked-test pool has category counts of 11 accommodation, 11 attraction, 15 dining, 19 shopping, and 24 transportation; any later 60-task composition and any 12-per-category top-up must be decided before unsealing.

**No paid DeepSeek calls, independent validation runs, or final-test runs were started in this stage.** The independent cohort remains unstarted.
