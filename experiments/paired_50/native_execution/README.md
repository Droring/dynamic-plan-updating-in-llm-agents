# Native CostBench checkpoint execution

This experiment runs DeepSeek through the **native CostBench tool implementations** from the frozen 50-task RETAIN/SWITCH study. It is a checkpointed continuation experiment: each trajectory starts from the same frozen checkpoint used by the paired decision dataset, and the model must execute tools until it reaches the task goal.

## What is reused from upstream CostBench

The adapter imports the pinned CostBench checkout and uses:

- **tools_ready_in_memory** to recreate each task's original tool registry and deterministic seed;
- the native **GroundtruthSolver** to reconstruct and audit each checkpoint and each condition;
- native **Tool / CompositeTool** objects and **generate_interface**;
- the original **QUERY_INSTRUCTION** prompt template;
- **env.run._execute_tool_simulation** for every model-selected tool call.

The upstream revision is fixed at 6424069f3f773ade076bcedbed302ed47cfb1837. The adapter does not edit upstream CostBench files.

## How the checkpoint is reconstructed

For each task, the runner:

1. Rebuilds the native tool registry at refinement level 2 with ban_longest_tool=True and seed 200000 + numeric_query_id.
2. Recomputes the initial native shortest path.
3. Replays the first tool in that path when the frozen fixture contains a prefix. Prefix inputs come from the source CostBench query's recorded TimeInfo, location_preference, and preference fields.
4. Checks the replayed output type and preference ID, then verifies the reconstructed type state and checkpoint SHA-256 against the frozen request and task registry.
5. Rebuilds the condition-specific visible tool set from the frozen model-visible tool metadata. Exactly one tool definition must have the changed value; the visible tool graph and incumbent suffix must remain paired.
6. Re-runs the native solver from the reconstructed checkpoint and verifies the RETAIN/SWITCH label before any model call.

The prefix is deterministic checkpoint setup, not a model-generated action in this experiment. The incumbent suffix is also solver-derived by the frozen dataset. The study therefore measures how the model acts when given an existing continuation plan at a controlled checkpoint; it does not measure whether a model independently invents that original plan.

## What the model sees and does

The model receives the original user request, the replayed prefix observation, the current available data types, and the incumbent remaining plan. It sees the current native CostBench tool interfaces. The RETAIN/SWITCH gold label and manifest are not included in its messages.

DeepSeek Flash runs at temperature 0 with thinking disabled. The adapter makes one tool call per step, executes it through CostBench's native simulation helper, updates the same type-state abstraction used by the upstream harness, and continues until the goal type is reached or the step limit is hit.

The first executed tool is the observable action measure:

- first tool equals the incumbent suffix's first tool: **RETAIN**;
- first tool differs: **SWITCH**;
- no tool call: no first-action label.

The full path relation and goal-state success are reported separately. This avoids treating an initial RETAIN action as proof that the model never replanned later.

## Offline validation

Use Python 3.12 and a local CostBench checkout at the pinned revision.

~~~bash
git clone https://github.com/JiayuJeff/CostBench.git ../CostBench
git -C ../CostBench checkout 6424069f3f773ade076bcedbed302ed47cfb1837
python -m pip install -r ../CostBench/requirements.txt numpy
(
  cd ../CostBench
  # The pinned source checkout has no persisted test-mode ID state.
  test ! -e env/data/runtime/id_history/id_generator_state_test.json
  python env/domains/travel/generate_search_space.py \
    --generate_test \
    --test_config_path env/domains/travel/travel_config.yaml \
    --num-times 5000 \
    --num-time-combinations 5000 \
    --seed 42
  cp env/data/static/search_spaces/test/search_space.json env/data/static/search_spaces/test_search_space.json
)
python -m unittest discover -s experiments/paired_50/native_execution -p 'test_*.py' -v
python experiments/paired_50/native_execution/run_official_harness.py --costbench-root ../CostBench
~~~

The search database is regenerated from the pinned travel configuration with the upstream seed and ID ordering used by the source queries. The output is copied to the runtime path expected by CostBench. The default harness command is a **dry run**. It reconstructs all 100 checkpoints, replays the prefixes, validates the paired tool graphs and gold labels with the native solver, and builds the official tool interfaces. It makes zero DeepSeek API calls.

## Full-cohort results

The frozen 50-task cohort has completed all 100 native execution trajectories. All 100 reached the goal, and the first native tool action succeeded in all 100.

The first-action label is descriptive: RETAIN means the first executed tool equals the incumbent suffix's first tool; SWITCH means it differs. It is not a path-optimality judgment.

| Descriptive measure | Result |
|---|---:|
| RETAIN-condition trials whose first action followed incumbent | 48/50 (96%) |
| SWITCH-condition trials whose first action followed incumbent | 48/50 (96%) |
| Total first actions following incumbent | 96/100 (96%) |
| Total first actions departing from incumbent | 4/100 (4%) |
| Goal state reached | 100/100 |
| First native tool action succeeded | 100/100 |
| Exact incumbent suffix executed | 96/100 |
| Alternative continuation observed | 4/100 |

The model followed the incumbent first action in 48/50 SWITCH conditions. This is evidence of strong incumbent persistence in this protocol. The four deviations are not counted as successful switches without a separate comparison against the current-condition optimum.

The paired first-action outcomes were 47 RETAIN/RETAIN, one RETAIN/SWITCH, one SWITCH/RETAIN and one SWITCH/SWITCH. Only one pair showed the expected first-action distinction across conditions. This is a behavioral result, not a path-optimality score.

The archived merged artifact was recovered from the retired repository and inspected offline. Its raw per-trajectory records are not yet committed in this repository. The summary, runner, frozen requests and validation tests are available here; the historical artifact contains `RESULTS.md`, `scores.json`, `ledger.json` and `responses.jsonl`.

The [native path-value audit](NATIVE_PATH_VALUE_AUDIT.md) replays all 100 executed paths, validates every recorded tool value against the frozen tool registry, and compares each path with the current-condition native optimum. An independent Dijkstra implementation matches the pinned solver's optimal path value in all 100 trials. The audit finds 48/50 value-optimal RETAIN paths and 2/50 value-optimal SWITCH paths. First actions account for 83.7% of total path regret; later actions account for 16.3%.

The [mechanism analysis](MECHANISM_ANALYSIS.md) examines whether the changed tool belongs to the incumbent suffix, whether it is the first or a later action, and whether the paired first action changes in the expected direction.

The initial run completed 66 trajectories and stopped during the next one at the token reservation guard. A continuation completed that same frozen trial from its checkpoint and the remaining 33 trials. The merge script validates the two run artifacts against frozen request and manifest hashes, scores each of the 100 unique trials once, and separately accounts for the superseded partial attempt.

- Scored provider usage: **1,191,160 tokens** across 287 model calls.
- Superseded partial attempt: **5,688 tokens** across one model call.
- Total provider usage across both runs: **1,196,848 tokens**.
- API errors: 0.
- Runner errors: 0.
- Incomplete trajectories in the scored cohort: 0.

- [Committed results summary](RESULTS.md)
- [Native 100-trajectory path-value audit](NATIVE_PATH_VALUE_AUDIT.md)
- [Offline audit implementation](native_path_value_audit.py)


## Candidate-decision localization (offline preparation)

The [candidate diagnostic protocol](CANDIDATE_DECISION_DIAGNOSTIC.md) separates explicit candidate reporting, comparison with a fixed feasible candidate menu, and the conversion of a selected candidate into a native tool action. The [offline prompt builder](prepare_candidate_diagnostic.py) reconstructs all 16 frozen checkpoints and uses the pinned native solver to validate candidate feasibility and first-action ties. It prepares 75 diagnostic prompt variants across 15 first-action-eligible checkpoints; Query00403 remains a separate path-level exception. **The builder does not call DeepSeek; these diagnostics have not yet been measured.**

~~~bash
python experiments/paired_50/native_execution/prepare_candidate_diagnostic.py --costbench-root ../CostBench --out candidate_diagnostic_dry_run.json
~~~

**Completed real-model diagnostic:** [candidate-decision results](CANDIDATE_DECISION_RESULTS.md) — 75/75 requests, 415,040 tokens, 0 API errors; SWITCH optimal alternatives explicitly reported 6/7, supplied-menu comparison correct 6/14, native action correct 6/14. These are 8 reused tasks, not a held-out algorithm benchmark.\n\n**Native full trajectories:** [results](FULL_TRAJECTORY_COMPARISON_RESULTS.md), [frozen protocol](FULL_TRAJECTORY_COMPARISON_PROTOCOL.md), [execution runner](run_full_trajectory_comparison.py). On 30 native trajectories across 5 tasks, all methods reached goals; the candidate-gate and incumbent arms each achieved 5/10 reference-optimal complete paths, compared with 7/10 for unrestricted graph planning. **First-action accuracy improvement did not establish complete-path improvement.**\n\n**Bounded candidate verifier:** [results](BOUNDED_VERIFIER_RESULTS.md), [implementation](bounded_candidate_verifier.py), [independent confirmation manifest](BOUNDED_VERIFIER_CONFIRMATION_MANIFEST.json). The bounded, candidate-restricted path verifier attained 75% balanced first-action accuracy on both 8-task development and 10-task disjoint confirmation cohorts, preserving 100% RETAIN in both; the result is a graph-planning-assisted baseline, not full-trajectory or general-agent performance.\n\n**Counterfactual verification gate:** [results](COUNTERFACTUAL_GATE_RESULTS.md), [protocol](COUNTERFACTUAL_GATE_PROTOCOL.md). A separate DeepSeek review rejected all 16 distinct no-plan candidate proposals, including 6/6 solver-optimal proposals in SWITCH; balanced accuracy stayed at 56.25%. The gate reused archived C candidates and did not run new complete trajectories.\n\n**Balanced-replanning pilot:** [native results](BALANCED_REPLANNING_RESULTS.md) and [frozen protocol](BALANCED_REPLANNING_PROTOCOL.md). Two plan-preserving comparison interventions were tested in 64 native first-action trials; neither improved SWITCH and one worsened RETAIN. See report for per-task results.\n\n### Running the candidate diagnostics

The [candidate-decision workflow](../../../.github/workflows/candidate-decision-diagnostic.yml) is intentionally **manual-only**. In GitHub Actions, select **Candidate-decision mechanism diagnostic** → **Run workflow**, select `main`, tick `run_paid_diagnostic`, then launch. The paid job is bounded to 75 diagnostic requests and a 600,000-token cap, with exact prompts, responses, native tool observations, and per-checkpoint scoring saved in the `candidate-decision-results` artifact. An unavailable API key stops the job before paid execution. The diagnostic is exploratory, reuses eight previously examined tasks, and does not validate a new algorithm.

The three endpoints are fresh, separate model sessions. The text-only endpoints receive read-only copies of current native tool definitions; the execution endpoint receives callable native tools. Any difference across these endpoints may reflect both the task instruction and response modality, so paired results must be interpreted as *diagnostic*, not as proof of hidden cognitive stages.

## Paid execution

Set DEEPSEEK_API_KEY in the shell, then start with one complete pair (two trajectories):

~~~bash
python experiments/paired_50/native_execution/run_official_harness.py --costbench-root ../CostBench --live --limit 2 --cap 150000 --out experiments/paired_50/native_execution/live_results/pilot_pair_01
~~~

Only after reviewing the pilot should the full 100-trial run be started:

~~~bash
python experiments/paired_50/native_execution/run_official_harness.py --costbench-root ../CostBench --live --limit 100 --cap 800000 --out experiments/paired_50/native_execution/live_results/full_100
~~~

The runner is sequential, records provider token usage, checks a per-call reservation against the configured cap, writes each completed trajectory immediately, and does not retry failed API calls. A nonempty output directory is rejected to prevent accidental duplicate runs. If a run stops at `reservation_cap`, use `--resume-from PATH_TO_PREVIOUS_OUTPUT` with a larger cumulative `--cap`; the runner validates the saved hashes and reconstructs the already executed native tool trace so it can continue without repeating those tool calls.

Outputs:

- **responses.jsonl** — per-trial tool calls, observations, first-action classification, goal state, and provider usage;
- **scores.json** — incumbent-following/deviation counts by condition, paired first-action behavior, trajectory relations, and goal-state completion;
- **ledger.json** — run status, attempted trials, reserved/charged tokens, input hashes, and cap.

The offline-validation workflow runs tests and the full dry-run reconstruction without API calls. The separately named paid-execution workflows call DeepSeek; their jobs are gated to manual dispatch after the initial one-off runs.
