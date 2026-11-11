# Complete Candidate Verification and Strict Plan Replacement

This module contains the ordinary Fresh complete-candidate baseline and the experimental bounded type-contract local-substitution method for CostBench. Historical experiment scripts and the frozen 32-trajectory records remain unchanged.

## Ordinary Fresh baseline

1. Reconstruct the checkpoint from the current typed state and exact successful native observations. Keep the incumbent remaining plan available to the deterministic selector, but do not expose it to the Fresh candidate prompt.
2. Make exactly one Fresh planning request for one complete ordered tool path.
3. Validate only the submitted sequence against current public tool preconditions, effects, goal completion, and current path value. The checker does not search, expand, or complete a candidate.
4. Retain a feasible incumbent on a tie or when the submitted candidate is not a feasible strict improvement. Switch only to a submitted feasible complete path with strictly lower current path value. Stop if neither incumbent nor candidate is feasible.
5. Commit the selected complete path to the state-bound executor. The LLM generates arguments only for the exact next committed tool.
6. Advance the cursor only after a successful native return and matching observed typed-state update. A failure or tool-catalogue change invalidates the certificate.

This is the ordinary complete-candidate reference arm, not the new method. A malformed or infeasible Fresh candidate is not silently repaired or retried.

## Experimental method: bounded type-contract local substitution

The new experimental strategy is fresh_with_local_substitution. It makes the same single Fresh planning request as the ordinary baseline, then searches a fixed local neighborhood around only two anchors: the incumbent remaining plan and the Fresh complete proposal.

- A replaced segment contains at most four consecutive tools.
- A replacement sequence contains at most two currently available tools.
- Replacement tools must satisfy their input-type requirements from the segment's starting state.
- The replacement sequence must produce the original segment's boundary output type.
- Every spliced complete path is passed through the unchanged submitted-path checker.
- The strict selector retains on ties and switches only to a strictly better feasible complete path.
- The selected full path is committed and executed through the existing state-bound executor.

This is a bounded symbolic search over public tool contracts, not unrestricted graph planning. It makes no additional model calls and does not receive condition labels, oracle paths, or scoring values. Its search bounds are fixed and must not be tuned on validation or test tasks.

The retrospective development audit and limitations are documented in [LOCAL_SUBSTITUTION_MECHANISM.md](LOCAL_SUBSTITUTION_MECHANISM.md). The eight development tasks were reused to design the operator; their results are not independent validation.

## Historical 32-trajectory development screen

The frozen 32-trajectory development screen compared repair_plus_fresh against fresh_plus_fresh. Both methods achieved 75.0% execution-grounded BA, RETAIN 8/8, SWITCH 4/8, Pair Accuracy 50.0%, and 100% goal success. Their selected plans and executed paths matched in all 16 matched task-condition comparisons. Repair added no unique strict-better SWITCH candidate.

The original repair_plus_fresh arm is retained only as historical evidence. It is not the new method. The first Fresh proposal from the archive is used in the retrospective local-substitution audit; oracle values remain post-hoc scoring fields.

Historical records, prompts, provider events, native events, and the frozen schedule remain archived in [GitHub Actions run 43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958). The result report is [DEVELOPMENT_SCREEN_RESULTS.md](DEVELOPMENT_SCREEN_RESULTS.md).

## Module map

- policy_input.py: policy whitelist and observation-grounded state reconstruction.
- candidate_generator.py: complete-path parsing and candidate request logging.
- submitted_plan_checker.py: submitted-path-only validation and strict selection.
- local_plan_substitution.py: bounded type-contract replacement around supplied complete paths.
- update_controller.py: ordinary Fresh baseline, local-substitution strategy, and explicit historical replay modes.
- committed_plan_executor.py: state-bound plan certificate, exact tool order and cursor.
- costbench_adapter.py: adapter around the pinned native CostBench execution helper.
- run_complete_candidate.py: candidate generation, strict selection, argument generation, native execution, DeepSeek-compatible adapters, and provider-free native smoke path.
- scoring_logging.py: post-hoc decision/execution scoring and durable records.
- provider.py: shared token cap, pre-request reservations, durable request events, and no-retry handling for uncertain provider outcomes.
- run_development_screen.py: frozen 32-cell historical runner; live execution requires explicit --execute.
- dry_run.py: provider-free one-candidate end-to-end dry run.

## Offline validation

From the repository root:

~~~bash
python -m unittest research.complete_candidate_verification.test_protocol -v
python -m unittest research.complete_candidate_verification.test_local_plan_substitution -v
python -m unittest research.complete_candidate_verification.test_development_screen_local_substitution -v
python -m unittest research.complete_candidate_verification.test_runner -v
python -m unittest research.complete_candidate_verification.test_costbench_native -v
python -m unittest research.complete_candidate_verification.test_provider -v
python -m unittest research.complete_candidate_verification.test_development_screen -v
python -m research.complete_candidate_verification.dry_run
~~~

The retrospective fixture test uses archived development prompts and responses converted to policy-visible typed contracts. It replays no provider request. The protocol, runner, provider and synthetic dry-run tests require no provider client, API key, or model call. The pinned native integration tests also make zero provider calls, but require COSTBENCH_ROOT and the generated CostBench test search database; the release-validation workflow prepares both.

## Data separation

The policy input type has no condition, oracle, regret, reference-path, or answer-key fields. The retrospective audit fixture stores condition and oracle values only in its scoring layer; the test constructs PolicyInput without those fields. The evaluator may consume condition labels and the official optimum only after selection. The checker receives only the submitted path and public tool interfaces; it never imports a graph-search routine or a ground-truth solver.

## Pinned native CostBench integration

With the pinned CostBench checkout and generated search database available:

~~~bash
python -m research.complete_candidate_verification.run_complete_candidate \
  --costbench-root ../CostBench \
  --condition RETAIN
~~~

The default runs one Fresh candidate request and then executes the complete selected path through the official native tool helper using local deterministic argument responses. It makes zero provider calls. The historical repair_plus_fresh and fresh_plus_fresh options are available only for reproducing the completed development screen.

The pinned native integration suite also checks a SWITCH checkpoint in which the local-substitution method selects and executes a strictly better complete path.

## Independent validation plan

The next validation is frozen at **20 entirely new base tasks**, four per CostBench category, excluding all historical and derived tasks. The seven comparison arms are:

1. Original DeepSeek Agent.
2. Simple RETAIN rule.
3. Best existing prompt: A_original from the four-arm screen, selected by historical balanced accuracy; see [BEST_EXISTING_PROMPT_SELECTION.md](BEST_EXISTING_PROMPT_SELECTION.md).
4. Existing bounded verifier plus complete-plan handoff.
5. Ordinary Fresh full-candidate generation with the same checker and executor.
6. New method: fresh_with_local_substitution.
7. Full graph planning with the same executor.

This gives **280 trajectories** (20 tasks × RETAIN/SWITCH × seven methods). Use DeepSeek Flash, temperature 0, thinking disabled, and at most three planning calls per trajectory. Parameter-generation calls are counted separately and included in total usage. The total token ceiling and exact output-token settings must be fixed before any paid execution.

Go/no-go gates: RETAIN 20/20; SWITCH at least 14/20; balanced accuracy at least 85%; no result below the ordinary complete-candidate control; no regression in goal success or complete-trajectory quality.

The subsequent frozen test contains 60 entirely new tasks (12 per category), 840 primary trajectories, plus 120 preselected stability repeats. It remains sealed unless the independent validation passes.

The exact A_original prompt arm and category-specific system-prompt hashes are now frozen. The total token ceiling and maximum output settings remain to be set. No paid DeepSeek calls or independent validation runs have been launched.

## Current research status

- Phase 1, provider-free implementation: complete.
- Phase 2, 32-trajectory development screen: complete.
- Phase 3, 20-task seven-method independent validation: not started.
- Phase 4, 60-task frozen test: not started.

The bounded local-substitution method has passed offline implementation and native integration checks. Its effectiveness on independent tasks is not yet established.
