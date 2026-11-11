# Complete Candidate Verification and Strict Plan Replacement

This module implements the current simplified candidate-verification policy for
CostBench. Historical experiment scripts and the frozen 32-trajectory records
remain unchanged.

## Current simplified method

1. Reconstruct the checkpoint from the current typed state and exact successful
   native observations. Keep the incumbent remaining plan available to the
   deterministic selector, but do not expose it to the Fresh candidate prompt.
2. Make exactly one Fresh planning request for one complete ordered tool path.
   The model must submit the whole path; it receives no reference answer, optimal
   path, condition label, or scoring field.
3. Validate only the submitted sequence against current public tool preconditions,
   effects, goal completion, and current path value. The checker does not search,
   expand, or complete a candidate.
4. Retain a feasible incumbent on a tie or when the submitted candidate is not a
   feasible strict improvement. Switch only to a submitted feasible complete path
   with strictly lower current path value. Stop if neither incumbent nor candidate
   is feasible.
5. Commit the selected complete path to the state-bound executor. The LLM generates
   arguments only for the exact next committed tool.
6. Advance the cursor only after a successful native return and matching observed
   typed-state update. A failure or tool-catalogue change invalidates the certificate.

The current policy makes one planning call per trajectory. Parameter-generation
calls are separately recorded and included in total model-call and token usage.
A malformed or infeasible Fresh candidate is not silently repaired or retried.

## Historical development-screen replay

The completed 32-trajectory development screen compared `repair_plus_fresh`
against `fresh_plus_fresh`. Those explicit strategy modes remain available only
to reproduce the frozen historical run. They are not the default or current
simplified method.

The two Fresh prompts in the historical baseline were identical at temperature
zero. Raw artifact inspection found identical candidate paths in 15/16 matched
Fresh + Fresh task-condition cells. The only differing pair was Query00851 under
RETAIN; strict selection retained the incumbent either way. The second Fresh call
added no SWITCH coverage. Repair likewise added no unique strict-better SWITCH
coverage. These development findings motivate removing repeated candidate calls
from the active policy; they do not establish held-out performance.

Historical records, prompts, provider events, native events, and the frozen
schedule remain archived in [GitHub Actions run 43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958).
The result report is [DEVELOPMENT_SCREEN_RESULTS.md](DEVELOPMENT_SCREEN_RESULTS.md).

## Module map

- policy_input.py: policy whitelist and observation-grounded state reconstruction.
- candidate_generator.py: complete-path parsing and candidate request logging; legacy
  candidate interfaces support exact frozen-screen replay.
- submitted_plan_checker.py: submitted-path-only validation and strict selection.
- update_controller.py: one-call Fresh policy plus explicit historical replay modes.
- committed_plan_executor.py: state-bound plan certificate, exact tool order and cursor.
- costbench_adapter.py: adapter around the pinned native CostBench execution helper.
- run_complete_candidate.py: candidate generation, strict selection, argument generation,
  native execution, DeepSeek-compatible adapters, and provider-free native smoke path.
- scoring_logging.py: post-hoc decision/execution scoring and durable records.
- provider.py: shared token cap, pre-request reservations, durable request events, and
  no-retry handling for uncertain provider outcomes.
- run_development_screen.py: frozen 32-cell historical runner; live execution requires
  explicit `--execute`.
- dry_run.py: provider-free one-candidate end-to-end dry run.

## Offline validation

From the repository root:

```bash
python -m unittest research.complete_candidate_verification.test_protocol -v
python -m unittest research.complete_candidate_verification.test_runner -v
python -m unittest research.complete_candidate_verification.test_costbench_native -v
python -m unittest research.complete_candidate_verification.test_provider -v
python -m unittest research.complete_candidate_verification.test_development_screen -v
python -m research.complete_candidate_verification.dry_run
```

The protocol and runner tests plus the synthetic dry run require no provider client,
API key, or model call. The pinned native integration test also makes zero provider
calls, but requires COSTBENCH_ROOT and the generated CostBench test search database;
the release-validation workflow prepares both.

## Data separation

The policy input type has no condition, oracle, regret, reference-path, or answer-key
fields. The evaluator may consume condition labels and the official optimum only
after execution. The checker receives only the submitted path and public tool
interfaces; it never imports a graph-search routine or a ground-truth solver.

## Full native CostBench smoke test

With the pinned CostBench checkout and generated search database available:

```bash
python -m research.complete_candidate_verification.run_complete_candidate \
  --costbench-root ../CostBench \
  --condition RETAIN
```

The default runs one Fresh candidate request and then executes the complete selected
path through the official native tool helper using local deterministic argument
responses. It makes zero provider calls. The historical `repair_plus_fresh` and
`fresh_plus_fresh` options are available only for reproducing the completed
development screen.

## Frozen 32-trajectory development screen

The frozen schedule and results are historical development evidence, not a held-out
estimate. The 32 trajectories were 8 previously explored base tasks × 2 conditions
× 2 methods. Both historical methods achieved 75.0% execution-grounded BA, RETAIN
8/8, SWITCH 4/8, Pair Accuracy 50.0%, and 100% goal success. Their selected plans
and executed paths matched in all 16 matched task-condition comparisons. The
candidate-generation diagnosis and baseline caveat are documented in
[DEVELOPMENT_SCREEN_RESULTS.md](DEVELOPMENT_SCREEN_RESULTS.md).

The historical screen is not being rerun during simplification. No new API calls
or new task conditions are part of this phase.
