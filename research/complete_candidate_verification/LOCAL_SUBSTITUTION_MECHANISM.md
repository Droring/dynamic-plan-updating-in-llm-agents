# Bounded Type-Contract Local Substitution

**Status: implemented as an experimental strategy; offline CI and one pinned native integration are pending. No independent evaluation has started.**

## Motivation from the frozen development screen

The 32-trajectory screen produced four incorrect SWITCH decisions. All submitted candidates were complete, feasible, and executed exactly as committed. The strict selector retained the incumbent because none of the model-generated candidates had a lower current path value.

The Fresh prompt did not include the incumbent plan, so these four failures cannot be attributed solely to direct exposure to the old plan. The evidence instead points to incomplete coverage of equivalent tool compositions in the current tool catalogue. This is a development-cohort diagnosis, not a general claim about LLM plan commitment.

## Retrospective path audit

The archived 32-trajectory artifact was analyzed offline. For each of the eight SWITCH checkpoints, the typed tool catalogue was used to reconstruct a shortest feasible path for audit only. The experimental policy does not receive that oracle path or its value.

| Query | Incumbent value | Fresh candidate value | Audited best value | Local-substitution finding |
|---|---:|---:|---:|---|
| Query00178 | 77.35 | 77.65 | 76.05 | Search + three-step finish |
| Query00351 | 58.66 | 59.08 | 57.36 | Direct three-step finish |
| Query00440 | 61.51 | 60.21 | 60.21 | Fresh path already best |
| Query00549 | 79.09 | 79.13 | 77.79 | Search-to-step-1 + finalize |
| Query00598 | 62.55 | 61.37 | 61.25 | Step-1 refinement + finalize |
| Query00662 | 62.01 | 60.71 | 60.71 | Fresh path already best |
| Query00689 | 78.99 | 79.41 | 77.69 | Search + three-step finish |
| Query00851 | 84.04 | 82.92 | 82.74 | Search-to-step-1 + step-2 refinement + select |

The bounded substitution prototype, with a maximum replaced segment of four tools and a maximum replacement sequence of two tools, recovered a path matching the audited best value in all eight development SWITCH cases. This is a retrospective result on the same eight development tasks used to diagnose and shape the operator. It is not an estimate of independent performance and must not be reported as one.

## Method definition

The experimental strategy is `fresh_with_local_substitution`:

1. Reconstruct the current typed state and incumbent suffix from confirmed observations.
2. Make exactly one Fresh request for a complete candidate path.
3. Use the incumbent and any syntactically complete Fresh proposal as anchors.
4. For every contiguous anchor segment of at most four tools, record the segment's start state, cumulative value, and final output type.
5. Enumerate replacement sequences of at most two currently exposed tools. Each replacement tool must have all required input types available at that point. The replacement sequence must produce the original segment's boundary output type.
6. Splice the replacement into the original path and validate the entire resulting path using the existing submitted-path checker. This rejects missing suffix inputs, invalid ordering, paths that stop short of the goal, and actions after goal completion.
7. Pass the Fresh proposal and all validated local alternatives to the unchanged strict selector. Retain on ties; switch only to a strictly better complete path.
8. Commit and execute the exact selected path with the existing state-bound executor.

The checker remains verification-only. The local operator is a separate bounded candidate generator, not a hidden path-completion feature in the checker.

## Difference from full graph planning

The local operator is anchored to one or two supplied complete paths: the incumbent and one Fresh proposal. It only substitutes a contiguous segment of at most four tools with a sequence of at most two tools that reaches the same typed boundary. It does not enumerate arbitrary paths from the initial checkpoint to the goal.

The planned full-graph comparator remains a separate method that searches the reachable typed state space from the checkpoint. The two methods must remain separate experimental arms.

## Information boundary and budget

The operator reads only public current tool contracts: required input types, output type, and current per-tool value. It does not read condition labels, answer keys, reference paths, oracle values, or evaluation scores. It makes no model calls. The complete strategy uses one Fresh planning call plus the existing argument-generation calls for the committed path.

The fixed neighborhood bounds are four tools per replaced segment and two tools per replacement sequence. They must not be tuned after inspecting the independent 20-task outcomes.

## Limitations to test

- The current CostBench typed-state model is monotonic and each tool exposes one output type in its public description. Environments with state deletion, side effects, or argument-dependent output types need a different contract model.
- A better path may require replacing more than four contiguous tools or more than two tools. The method intentionally will not discover all possible plans.
- The operator relies on the public type contracts and values being complete and current. Catalogue changes invalidate the existing execution certificate.
- Retrospective success on eight development tasks may reflect the simple repeated tool-pattern structure of this cohort.

## Next validation gate

Before the 20-task independent protocol can start, the following must pass:

- unit tests for single-tool and two-tool substitutions, strict-improvement filtering, suffix feasibility, deterministic ordering, and fixed search bounds;
- end-to-end mocked execution proving the derived path is exactly the committed and executed path;
- pinned native CostBench integration with zero provider calls;
- full release validation and repository structure checks.

The independent 20-task protocol remains frozen and unstarted. No DeepSeek API calls, new tasks, or 60-task test runs are authorized by this report.
