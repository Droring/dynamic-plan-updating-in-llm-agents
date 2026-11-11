# Method Simplification and Offline Regression Acceptance

**Status: PASS for implementation and offline regression. NO-GO for treating this version as a distinct new algorithm.**

## Scope

This stage followed the completed 32-trajectory development screen. It made no
DeepSeek API calls, added no tasks, changed no historical records, and did not
start the independent 20-task validation or the 60-task frozen test.

Repository: `Droring/dynamic-plan-updating-in-llm-agents`

Branch: `research/complete-candidate-verification`

Implementation commit: `f49f33e4acae1143b9fc10fea77c7bf5d1ab7b5c`

## Evidence used to simplify

The raw artifact from [development-screen run 43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958) was inspected, including the per-trajectory candidate proposals.

For the 16 Fresh + Fresh task-condition cells:

- 15/16 pairs produced identical candidate paths.
- The only differing pair was Query00851 under RETAIN.
- Strict selection retained the incumbent in that cell either way.
- The second Fresh call added no SWITCH coverage.

The same development report shows that Repair added no unique strict-better SWITCH candidate. These findings support removing redundant candidate-generation branches from the active policy. They do not establish held-out performance.

## Implemented simplification

The active default now:

1. Generates one Fresh complete candidate without exposing the incumbent plan.
2. Validates only the submitted complete path against current public tool contracts.
3. Retains a feasible incumbent on ties and switches only to a strictly lower-value feasible complete candidate.
4. Commits the selected full path to the existing state-bound executor.
5. Generates arguments only for the committed next tool and advances only after successful native state confirmation.

The active policy makes exactly one planning call. An infeasible or malformed candidate is not silently retried or revised.

The frozen `repair_plus_fresh` and `fresh_plus_fresh` code paths remain explicitly available for historical development-screen reproduction. They are not the default active method. The original prompts, responses, schedules, provider events, native events, and reports remain unchanged.

## Files changed

- `research/complete_candidate_verification/update_controller.py`: added the one-call Fresh-only active policy; kept explicit historical replay modes.
- `research/complete_candidate_verification/run_complete_candidate.py`: changed the default strategy and provider-free native smoke expectation to one planning call.
- `research/complete_candidate_verification/dry_run.py`: changed the deterministic mock to return a strict-better candidate in one call and assert one planning call.
- `research/complete_candidate_verification/test_protocol.py`: added one-call switch, tie, no-retry, prompt-whitelist, and historical-replay checks; corrected the Fresh baseline test to assert identical prompts.
- `research/complete_candidate_verification/test_runner.py`: verified one candidate request, incumbent exclusion from the Fresh prompt, complete plan commitment, and native execution.
- `research/complete_candidate_verification/test_costbench_native.py`: updated the pinned native smoke expectation to one planning call.
- `research/complete_candidate_verification/README.md`: documented the active simplified method, historical replay boundary, and research interpretation.

## Offline regression results

[Release Validation run 43059538598](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43059538598) completed successfully on the implementation commit. [Research structure validation run 43059538592](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43059538592) also completed successfully.

| Test group | Passed |
|---|---:|
| Protocol, policy-input, checker, selection, executor, scoring, and dry-run tests | 36 |
| Complete-candidate runner and mocked model-response tests | 8 |
| Provider budget, accounting, and uncertain-outcome tests | 4 |
| Frozen historical development-screen schedule tests | 2 |
| Pinned official CostBench native multi-step integration | 1 |
| Existing repository script regression suite | 40 |
| **Total** | **91** |

Additional checks completed:

- Release manifest and release-integrity checks passed.
- Markdown link validation passed.
- Pinned official CostBench revision was checked out and used for native integration.
- Development-screen preflight completed with no provider calls.
- Provider-free dry-run passed and asserted zero provider calls.
- Native CostBench smoke trajectory reached the goal with zero provider calls and one planning call.
- Historical replay modes and frozen schedule tests remained operational.
- No API retry or live model request was made during simplification.

## Interpretation and stop decision

The simplified implementation is now the ordinary single-Fresh complete-candidate baseline combined with the same checker, strict selector, and committed-plan executor. It does not retain a distinct intervention that separates it from the planned ordinary-candidate comparison arm.

Therefore:

- **Implementation acceptance: PASS.**
- **Offline regression acceptance: PASS.**
- **Claim of a distinct new algorithm: NOT ESTABLISHED.**
- **Start the 20-task independent validation with duplicate method arms: NO-GO.**
- **Start the 60-task frozen test: NOT AUTHORIZED.**

This does not change the frozen evaluation protocol. It prevents spending the independent cohort on a comparison whose proposed method and ordinary-candidate baseline no longer represent distinct treatments. The one-call policy can remain as a reproducible baseline, but it should not be reported as a newly validated algorithm.

## Overall project progress

Using the four major stages with equal weight:

| Stage | Completion |
|---|---:|
| Phase 1 — provider-free implementation | 100% |
| Phase 2 — 32-trajectory development screen | 100% |
| Phase 3 — 20-task independent validation | 0% |
| Phase 4 — 60-task frozen test | 0% |
| **Overall** | **50%** |

The method-simplification and offline-regression substage is complete at 100%. The independent validation remains unstarted and should stay on hold until a distinct method exists.


## Follow-on method development: bounded local substitution

The NO-GO above remains the correct conclusion for the one-call Fresh-only policy
as a purported new algorithm. A separate intervention was subsequently added:
fresh_with_local_substitution. It uses one Fresh complete-path proposal and
bounded type-contract replacements around the incumbent and Fresh paths.

A retrospective audit fixture now tests all 16 RETAIN/SWITCH checkpoints from the
archived 32-trajectory development cohort with the repository implementation.
The method retained all eight RETAIN incumbents and selected an audited-optimal
complete path in all eight SWITCH checkpoints. The Fresh proposal itself was
already optimal in two SWITCH tasks; local substitution supplied the optimum in
the other six. These are reused development tasks and do not establish independent
effectiveness.

The offline release-validation workflow also verifies:
- six focused local-substitution unit tests;
- one retrospective test covering all 16 archived development checkpoints;
- nine end-to-end runner tests;
- two pinned native CostBench integration tests, including execution of a better
  SWITCH continuation with zero provider calls;
- the remaining protocol, provider, schedule, and repository regression suites.

The current independent validation now has 20 selected tasks from the pre-allocated
40-task Validation split, four per CostBench category, with seven comparison arms
and 280 planned trajectories. The selected cohort is disjoint from the historical
50-task and 80-task cohorts and from the development prompt/algorithm screens. The new
method occupies the previously reserved "New Method" arm. The exact archived
prompt for the "Best Existing Prompt" arm and its hash must be frozen before
the task manifest is released. The final 60-task test remains sealed until the
independent validation passes.

No paid DeepSeek calls have been made for this follow-on method development.
The overall four-stage project remains at 50%: implementation and development
screen are complete; independent validation and final test have not started.
