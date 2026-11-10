# Four-arm plan-influence screening protocol

## Status
Offline protocol and task manifest frozen. No provider calls have been launched. This is a new intervention on eight reused tasks from the existing paired-50 cohort, not an independent held-out evaluation.

## Research question
At the same current CostBench checkpoint, does showing the solver-supplied incumbent plan change the quality of the next native tool action, and does repeating the changed tool's current cost in the user message improve its salience?

## Naming and provenance decision
The paired-50 fixtures provide matched RETAIN/SWITCH current environments, a solver-derived incumbent suffix, and current tool costs. They do not provide a verified temporal old-price snapshot for every task. Therefore this experiment is named **information localization**, not an old-to-new event-history intervention. The explicit arm names the changed tool and repeats its current cost exactly as present in the current tool interface. It does not invent an old value or describe the paired counterfactual cost as a historical price.

The incumbent suffix is solver-derived, not Agent-authored. This experiment estimates the effect of displaying that supplied plan cue, not a self-authored commitment effect.

## Task sample
Eight tasks are frozen in `FOUR_ARM_TASK_MANIFEST.json`: four where the changed tool occurs in the incumbent suffix and four where it does not. All five CostBench task categories are represented. Within each predeclared category-by-relation stratum, the lexicographically first task ID was selected. Selection does not use model outcomes.

## Factorial conditions
A 2 x 2 design:
- **A — Original:** incumbent shown; original checkpoint update wording.
- **B — Current-cost reminder:** incumbent shown; add one neutral sentence naming the changed tool and its current cost. The same current costs are already visible in all tool descriptions, so this is a salience reminder, not new information.
- **C — Plan omitted:** remove only the incumbent-plan sentence; retain task, prefix, observation, current state, tools and original update wording.
- **D — Plan omitted + current-cost reminder:** combine C and B.

The current-cost reminder must be factual and non-directive, e.g. `The currently available cost for TOOL_NAME is VALUE.` The current tool interface, including current costs for all tools, remains visible in every condition. Do not reveal RETAIN/SWITCH labels, oracle paths, path values, or recommend an action.

## Fairness checks
For every task and environment condition:
1. Same native checkpoint, completed prefix, observations, task request, current tool graph, tool schemas and goal.
2. B differs from A only by the localized current-fact sentence.
3. C differs from A only by removal of the incumbent-plan sentence and its plan-specific lead-in; no other history or observation is removed.
4. D combines the registered B and C edits.
5. Same model ID, temperature, thinking setting, response format, token budget, tool-call budget and scorer.
6. RETAIN and SWITCH arms are both retained. Invalid calls and no-action responses remain in the denominator and are reported separately.

Removing the plan changes context length and a visible cue; this is an operational plan-content ablation, not a pure psychological manipulation.

## Run size and order
Eight tasks x two environment conditions x four prompt conditions x two repetitions = **128 first-action requests**. Two debug tasks add 16 requests. Two preselected tasks may receive complete continuation runs (16 trajectories), but only after first-action results and usage are audited.

Within each task, randomize/interleave all eight condition cells for repetition 1 and repeat with a second balanced order. Save seed and dispatch order. Each request starts from a fresh session and the same checkpoint. Do not carry messages between conditions.

## Outcomes
Primary: current-optimal first-action correctness (including all tied optimal first actions) and first-action Bellman regret under the pinned native solver.
Secondary: incumbent first-action agreement; valid/invalid/no-action rates; RETAIN and SWITCH correctness separately; full-path optimality, goal reached and trajectory regret for continuation tasks; repeat consistency and provider usage.

A deviation from the incumbent is not automatically a correct SWITCH. A matching first action is not automatically an incorrect RETAIN. Use solver-optimal action sets and regret.

## Analysis
The independent unit is the base task. Report per-task paired differences and improved/unchanged/worsened counts. Repetitions and RETAIN/SWITCH arms are nested observations, not independent tasks. With eight tasks, emphasize descriptive effects and task-level patterns rather than significance claims.

Factorial contrasts: B-A (localization with plan); D-C (localization without plan); D-B (plan-cue removal under localized facts); C-A (plan-cue removal under original wording). Also report interaction. Do not infer a unique internal mechanism from a prompt effect.

## Stop and approval gates
Offline dry-run and exact prompt-diff tests must pass before paid calls. Estimate usage from the two-task debug run and show estimated cost before the formal run. No formal paid run until the user explicitly approves the estimated budget and 128-request run. Stop at the time cap and preserve partial and negative results.

## Executable entry point

The native first-action runner is `run_four_arm_experiment.py`. It reconstructs each frozen checkpoint through the pinned CostBench tool registry, builds the four prompt arms, requests one native tool call, executes that first call with CostBench's native simulation helper, and scores the action against the native optimal continuation value. It does not continue the trajectory in this phase.

Offline validation (no provider calls):

```bash
python experiments/paired_50/native_execution/run_four_arm_experiment.py \
  --costbench-root /path/to/CostBench \
  --task-limit 8
```

The planned two-task debug cohort deliberately includes one changed tool inside the incumbent and one outside it:

```bash
python experiments/paired_50/native_execution/run_four_arm_experiment.py \
  --costbench-root /path/to/CostBench \
  --task-ids Query00188,Query00347 \
  --repetitions 1
```

This prepares 16 debug cells but makes no API calls. Paid execution requires `--live`; the 128-request formal cohort and the 16-request debug cohort are separate invocations. Do not launch either paid invocation until the debug usage is reviewed and the user approves the estimated budget.

## Post-smoke clarification

The archived payload audit confirmed that all four conditions include complete tool descriptions with current costs for every tool. Consequently, B and D repeat the changed tool's current cost in the user message; they do not expose information absent from A and C. Interpret B-A and D-C as tests of a localized current-cost reminder/salience cue. See `SMOKE_TEST_REPORT.md` and `MECHANISM_AUDIT.md` for the archived evidence and candidate-feasibility audit.

