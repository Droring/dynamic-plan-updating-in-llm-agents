# Phase 1 Acceptance Report

**Status: PASS — minimum prototype implemented and validated offline.**

## Scope

Phase 1 is the provider-free minimum prototype. It ends when the candidate
generation, submitted-path validation, strict selection, complete-plan execution,
native CostBench integration, and offline regression checks work together.
The 32-trajectory development screen is a separate next phase and has not been
started.

No paid DeepSeek API calls were made for this phase.

## Implemented components

- Policy input whitelist built only from the user request, goal, observed typed
  state, incumbent remaining plan, and current public tool interfaces.
- State reconstruction that advances only after successful native tool outputs.
- Two candidate sources: incumbent-informed local repair and independent
  full replanning without the incumbent in its prompt.
- A hard maximum of three planning calls, with the third reserved for one
  concrete malformed/infeasible-candidate revision.
- Submitted-path-only checking. The checker validates the supplied sequence and
  does not search, complete, or expand it.
- Strict-better selection: a feasible incumbent is retained on ties; switching
  requires a submitted feasible complete path with strictly lower current value.
- Complete-plan commitment, next-tool-only argument generation, argument schema
  validation, exact execution order, and state-bound certificate invalidation.
- Native CostBench execution through the pinned official execution helper, with
  capture of the real output object and observed output identifier.
- Post-hoc decision/execution scoring, Balanced Accuracy and Pair Accuracy,
  token/call accounting, latency fields, and durable JSONL/JSON logging.
- DeepSeek-compatible candidate and argument request adapters. These adapters
  were verified with a stub client; no provider request was sent.

## Acceptance evidence

The release-validation workflow passed on the phase-one implementation:

- 27 protocol tests passed.
- 4 end-to-end runner tests passed, including strict SWITCH selection, parameter
  call accounting, native-failure handling, and DeepSeek request construction.
- 1 pinned native CostBench integration test passed. It selected a frozen
  RETAIN checkpoint with a multi-tool remaining path, executed the complete
  committed path through the official CostBench native helper, advanced state
  from captured native outputs, reached the goal, and made zero provider calls.
- The repository's existing script test suite passed: 40 tests.
- Research repository structure validation passed.
- Release manifest, integrity, Markdown-link, and pinned CostBench checks passed.

The pinned upstream CostBench revision remains the one recorded by the existing
native harness. Historical experiment scripts and the main branch were not modified.

## Interpretation boundary

This acceptance result establishes that the first-version mechanism is
implemented and can complete a provider-free native CostBench smoke trajectory.
It does **not** establish that DeepSeek will generate useful candidates, that
Balanced Accuracy has improved, or that the method outperforms the planned
baselines. Those are empirical questions for the next phase.

## Next planned phase

The next phase is the frozen 32-trajectory development screen:

8 tasks × 2 conditions × 2 methods = 32 complete trajectories.

It compares the proposed method against ordinary complete-candidate sampling
under the same checker, executor, and planning-call ceiling. Its pre-registered
development gates remain unchanged. No development trajectory is included in
this phase-one acceptance report.


## Subsequent development-screen status

The frozen 32-trajectory development screen was completed in GitHub Actions run
[43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958).
Both methods achieved 75.0% execution-grounded BA, RETAIN 8/8 and SWITCH 4/8;
their selected plans and executed paths matched in all 16 paired cells. The
repair candidate added no unique strict-better SWITCH coverage, so that version
did not proceed to its originally proposed 12-task pilot. A distinct bounded
type-contract local-substitution method was subsequently implemented and audited
retrospectively on all 16 development checkpoints. The agreed next independent
study is now 20 entirely new tasks across seven methods, not the superseded
12-task pilot. See [LOCAL_SUBSTITUTION_MECHANISM.md](LOCAL_SUBSTITUTION_MECHANISM.md).
