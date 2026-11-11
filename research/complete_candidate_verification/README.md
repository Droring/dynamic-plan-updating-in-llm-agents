# Complete Candidate Verification and Strict Plan Replacement

This isolated module implements the frozen first-version protocol for CostBench.
Historical experiment scripts are not modified.

## Frozen method

1. Build a policy input only from the task request, goal, observed typed state,
   exact successful native tool observations, actual incumbent remaining plan,
   and currently exposed tool interfaces. Historical observations are replayed
   into both planning and argument-generation contexts; evaluation labels and
   oracle fields are rejected recursively.
2. Proposed strategy: generate one local-repair candidate while showing the incumbent.
3. Proposed strategy: generate one full-replanning candidate without showing the incumbent.
   Matched baseline: make two separate full-replanning calls using the same fresh
   prompt, without showing the incumbent. At the frozen temperature 0 these are
   repeated calls, not independent stochastic samples. Both strategies share the
   same call budget, path checker, strict selection, and committed-plan executor.
4. Validate each submitted complete path deterministically. The checker does not
   search, expand, or complete a candidate.
5. Replace a feasible incumbent only when a submitted feasible complete path has
   strictly lower current path value. Ties retain the incumbent.
6. Submit the complete selected path to a cursor-controlled executor. The LLM
   generates arguments only for the next committed tool.
7. Advance the cursor only after a successful native return and matching observed
   typed-state update. A failure or tool-catalogue change invalidates the certificate.

A third planning call is permitted only once, and only to repair a concrete
malformed or infeasible candidate when no strict improvement has already been
found. A valid tie does not trigger another planning call. The maximum is three
planning calls per trajectory; parameter-generation calls are separately
recorded and included in total usage.

## Module map

- policy_input.py: whitelist and observed-state reconstruction.
- candidate_generator.py: repair/fresh/revision candidate interfaces and call budget.
- submitted_plan_checker.py: submitted-path-only validation and strict selection.
- update_controller.py: candidate orchestration and deterministic choice.
- committed_plan_executor.py: state-bound plan certificate, exact tool order and cursor.
- costbench_adapter.py: adapter around the pinned native CostBench execution helper.
- run_complete_candidate.py: full candidate-generation, strict-selection, argument-generation, and native-execution loop; includes DeepSeek-compatible call adapters and a provider-free native smoke path.
- scoring_logging.py: post-hoc decision/execution scoring and durable records.
- provider.py: shared token cap, pre-request reservations, durable request events, and no-retry uncertain-outcome handling.
- run_development_screen.py: frozen 32-cell counterbalanced runner; live execution requires explicit --execute.
- dry_run.py: provider-free end-to-end dry run.
- test_protocol.py: offline unit and protocol tests.

## Offline validation

From the repository root:

    python -m unittest research.complete_candidate_verification.test_protocol -v
    python -m unittest research.complete_candidate_verification.test_runner -v
    python -m unittest research.complete_candidate_verification.test_costbench_native -v
    python -m research.complete_candidate_verification.dry_run
    python -m unittest research.complete_candidate_verification.test_provider -v
    python -m unittest research.complete_candidate_verification.test_development_screen -v

The protocol and runner unit tests, plus the synthetic dry run, require no provider
client, API key, or model call. The pinned native integration test also makes zero
provider calls, but requires COSTBENCH_ROOT and the generated CostBench test
search database; the release-validation workflow prepares both.

## Data separation

The policy input type has no condition, oracle, regret, reference-path, or answer
key fields. The evaluator may consume condition labels and the official optimum
only after execution. The checker receives only the submitted path and public
tool interfaces; it never imports a graph-search routine or a ground-truth solver.

## Full native CostBench smoke test

With the pinned CostBench checkout and generated search database available:

    python -m research.complete_candidate_verification.run_complete_candidate \
      --costbench-root ../CostBench \
      --condition RETAIN

By default, the command selects a frozen RETAIN checkpoint whose remaining plan
contains at least two tools. Pass --query-id to select one specific checkpoint.
Use --candidate-strategy fresh_plus_fresh to run the matched ordinary-sampling
baseline with the same provider-free native smoke harness.

This runs the full incumbent path through the official native tool helper using
local deterministic planner/argument responses. It makes zero provider calls.

## Frozen 32-trajectory development screen

First run the offline preflight and materialize the exact schedule and prompts:

    python -m research.complete_candidate_verification.run_development_screen \
      --costbench-root ../CostBench \
      --out outputs/complete_candidate_development_screen

This command makes zero provider calls. Live execution requires an explicit
`--execute` flag. The runner refuses a nonempty output directory, uses the
pinned DeepSeek model with temperature 0 and thinking disabled, disables SDK
retries, reserves every request against the frozen 1.2M-token hard cap, and
durably records request-start events before sending. Provider/native uncertain
outcomes stop the run without retry. The 32 trajectories are 8 previously
explored base tasks × 2 conditions × 2 methods; they are development data, not
held-out evidence. The base task, not each trajectory, is the analysis unit.


## Development-screen result

The frozen 32-trajectory screen is complete. Both Repair + Fresh and Fresh + Fresh
achieved execution-grounded BA 75.0%, RETAIN 8/8, SWITCH 4/8, Pair Accuracy 50.0%,
and 100% goal success. Their selected plans and executed paths were identical in
all 16 matched task-condition cells. Repair + Fresh increased candidate-path
diversity but added no unique strict-better SWITCH candidate. Under the frozen
stop rule, do not proceed to the 12-task independent pilot with this version.

The complete analysis is in [DEVELOPMENT_SCREEN_RESULTS.md](DEVELOPMENT_SCREEN_RESULTS.md),
with machine-readable results in [DEVELOPMENT_SCREEN_RESULTS.json](DEVELOPMENT_SCREEN_RESULTS.json).
The original prompts, responses, provider ledger, native events and schedule are
archived in [GitHub Actions run 43050073958](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43050073958).
