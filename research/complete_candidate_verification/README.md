# Complete Candidate Verification and Strict Plan Replacement

This isolated module implements the frozen first-version protocol for CostBench.
Historical experiment scripts are not modified.

## Frozen method

1. Build a policy input only from the task request, goal, observed typed state,
   actual incumbent remaining plan, and currently exposed tool interfaces.
2. Generate one local-repair candidate while showing the incumbent.
3. Generate one independent full-replanning candidate without showing the incumbent.
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
- dry_run.py: provider-free end-to-end dry run.
- test_protocol.py: offline unit and protocol tests.

## Offline validation

From the repository root:

    python -m unittest research.complete_candidate_verification.test_protocol -v
    python -m unittest research.complete_candidate_verification.test_runner -v
    python -m unittest research.complete_candidate_verification.test_costbench_native -v
    python -m research.complete_candidate_verification.dry_run

Both commands must complete without a provider client, API key, or model call.

## Data separation

The policy input type has no condition, oracle, regret, reference-path, or answer
key fields. The evaluator may consume condition labels and the official optimum
only after execution. The checker receives only the submitted path and public
tool interfaces; it never imports a graph-search routine or a ground-truth solver.

## Full native CostBench smoke test

With the pinned CostBench checkout and generated search database available:

    python -m research.complete_candidate_verification.run_complete_candidate \
      --costbench-root ../CostBench \
      --query-id Query00178 \
      --condition RETAIN

This runs the full incumbent path through the official native tool helper using
local deterministic planner/argument responses. It makes zero provider calls.
The DeepSeek adapters are exposed for the subsequent development screen, but
this first implementation stage does not launch paid model experiments.
