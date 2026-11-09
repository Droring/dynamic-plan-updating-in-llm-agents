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

The frozen 50-task cohort has now completed all 100 native execution trajectories.

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | 48/50 (96%) |
| SWITCH first-action accuracy | 2/50 (4%) |
| Overall first-action accuracy | 50% |
| Paired RETAIN/SWITCH accuracy | 1/50 (2%) |
| Same decision in both paired conditions | 48/50 (96%) |
| Model predicted RETAIN | 96/100 (96%) |
| Always-RETAIN baseline accuracy | 50% |
| Goal state reached | 100/100 |
| Exact incumbent suffix executed | 96/100 |

The model selected the incumbent first action in **48 of 50 SWITCH conditions (96%)**. It predicted RETAIN in 96/100 trajectories. Its 50% overall accuracy exactly matches an always-RETAIN baseline on this balanced dataset. The first-action prediction was identical across the two conditions in 48/50 pairs. The paired outcomes were: 47 tasks predicted RETAIN in both conditions, one correctly distinguished RETAIN from SWITCH, one predicted SWITCH in both conditions, and one reversed the two decisions. Task completion was 100/100, so completion rate alone would hide the plan-commitment failure.

The first-action label is based on the first executed native tool compared with the incumbent suffix's first tool. Full trajectory relation and goal completion are reported separately.

The initial run completed 66 trajectories and stopped during the next one at the token reservation guard. A continuation completed that same frozen trial from its checkpoint and the remaining 33 trials. The merge script checks both run artifacts against the frozen request and manifest hashes, scores each of the 100 unique trials once, and separately accounts for the superseded partial attempt.

- [Committed results summary](RESULTS.md)
- [Full merged report and 100 raw traces](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42555294948)
- [Initial execution run](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42551169346)
- [Continuation run](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42552119882)
- [Offline tests and 100-checkpoint reconstruction](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42555277010)

The merged artifact contains `RESULTS.md`, `scores.json`, `ledger.json`, and `responses.jsonl`. Use `merge_split_run_results.py` to repeat the merge from the two source artifacts.

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
- **scores.json** — RETAIN/SWITCH first-action results, paired accuracy, trajectory relations, and goal-state completion;
- **ledger.json** — run status, attempted trials, reserved/charged tokens, input hashes, and cap.

The offline-validation workflow runs tests and the full dry-run reconstruction without API calls. The separately named paid-execution workflows call DeepSeek; their jobs are gated to manual dispatch after the initial one-off runs.
