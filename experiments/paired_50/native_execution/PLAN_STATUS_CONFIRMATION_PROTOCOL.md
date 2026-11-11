# Checkpoint-Level Plan-Status Annotation Confirmation

## Research question

When an LLM Agent receives the same complete planner-computed continuation from the same frozen checkpoint, does an explicit validity annotation on its earlier plan improve execution beyond the plan handoff alone?

This is a focused follow-up to the five-task Plan Handoff × State Tracking development screen. It isolates the additional contribution of prior-plan status information. It does not introduce a new algorithm.

## Experimental contrast

Both arms start from the exact same frozen native CostBench checkpoint and receive exactly the same:

- original task request and checkpoint history;
- solver-supplied incumbent plan;
- current native tool definitions and typed state;
- complete minimum-cost continuation independently computed from the current native tool graph;
- model, decoding settings, maximum output tokens, and native execution loop.

The only prompt difference is the prior-plan status value in the final message:

| Environment | UNMARKED arm | ANNOTATED arm |
|---|---|---|
| RETAIN | `UNSET` | `VALID` |
| SWITCH | `UNSET` | `STALE` |

`VALID` means the incumbent suffix is still minimum-cost from the frozen checkpoint. `STALE` means it remains feasible but a strictly cheaper feasible continuation exists. Ties count as `VALID`.

The status is computed offline from the pinned native CostBench tool graph. It is an **oracle-derived diagnostic annotation**. Both arms receive the same complete planner continuation, so this experiment tests whether the extra explicit validity label changes the Agent's execution. It does not measure a deployable LLM-only method and does not establish a model-internal commitment mechanism.

## Task selection

Use the existing paired 50-task CostBench cohort. Exclude tasks used in the four-arm mechanism screen, bounded-verifier confirmation, and the preceding five-task plan-handoff development screen.

Select the first two eligible task IDs in lexicographic order within each of the five CostBench categories. Eligibility is fixed before any new provider call and requires:

1. a valid paired frozen checkpoint with identical initial typed state and incumbent suffix across RETAIN and SWITCH;
2. the incumbent suffix is feasible from the checkpoint in both environments;
3. an independent reconstruction of the native graph optimum confirms that the incumbent is minimum-cost in RETAIN and strictly suboptimal in SWITCH.

If two eligible tasks cannot be found in every category, or any checkpoint/hash/value audit fails, stop before provider calls. Do not relax the selection rule after inspecting model outcomes.

This is a held-out task cohort for the plan-status intervention, not a new or unseen CostBench dataset. The selected tasks belong to the existing 50-task cohort, and the interpretation must remain within this benchmark and task-selection protocol.

## Frozen run matrix

- 10 base tasks (2 per category)
- 2 paired environments: RETAIN and SWITCH
- 2 status arms: UNMARKED and ANNOTATED
- 2 repetitions per task/environment/arm

Total: `10 × 2 × 2 × 2 = 80` full native continuation trajectories.

Model settings: DeepSeek Flash, temperature 0, thinking disabled, 2,048 maximum output tokens per call. Each arm starts from an independently reconstructed copy of the same frozen checkpoint and uses the same native tool registry for its environment.

Operational hard cap for this follow-up: 1,200,000 provider tokens. The previous orphaned attempt remains conservatively reserved at 1,000,000 tokens; the completed 80-trajectory development screen used 725,465 provider tokens. This hard cap remains within the previously approved total budget envelope. No automatic retries are permitted.

## Outcomes and analysis

Primary outcomes:

- complete continuation optimality (`continuation_regret = 0` within tolerance);
- mean realized continuation regret;
- goal completion, reported separately from optimality.

Secondary outcomes:

- first-action Bellman regret;
- full-path regret from the frozen checkpoint;
- incumbent-plan adherence and updated-plan adherence;
- model-call count, provider tokens, elapsed time, invalid actions, and halt reason.

Compare ANNOTATED against UNMARKED within each task and environment. Report per-task paired differences and task-level means. The independent statistical unit is the base task (`n=10`); repetitions and RETAIN/SWITCH conditions are nested and paired, not independent samples. Report RETAIN and SWITCH separately as well as a balanced summary. Do not infer synergy or broad generalization from this two-arm experiment.

## Decision rules

- Annotation improves SWITCH without degrading RETAIN: evidence that explicit prior-plan status helps this controlled checkpoint-level interface; confirm on a further task cohort before proposing a method.
- Annotation improves RETAIN but not SWITCH: the label may help preserve valid plans but does not resolve switching.
- Annotation improves SWITCH but harms RETAIN: the label is not sufficiently calibrated for selective replanning.
- No consistent task-level benefit: the complete planner continuation likely explains the earlier B-arm gain; do not add a status module.
- Both arms remain suboptimal: inspect action-level loss and execution adherence; do not immediately design a new algorithm.
- Both arms are optimal: the status annotation is unnecessary in this task family; accept the simpler full-plan handoff result.

## Reproducibility and repository rules

- Keep all changes and results on the existing `main` branch. Do not create another branch.
- Pin CostBench to `6424069f3f773ade076bcedbed302ed47cfb1837`.
- Commit the selected task manifest before paid execution.
- Archive frozen requests, exact prompt hashes, responses, call-event journal, token ledger, and summary.
- The offline preparation and dry run must make zero provider calls.
- Any incomplete run is not a result. Do not replay a trial with an uncertain provider outcome; preserve the ledger and reconcile before any recovery.
