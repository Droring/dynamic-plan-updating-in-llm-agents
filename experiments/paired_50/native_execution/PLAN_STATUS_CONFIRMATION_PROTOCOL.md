# Plan-Status Annotation Confirmation

## Research question

After the same nonterminal action, does explicitly annotating the validity of the previous plan improve complete continuation execution **beyond providing the same complete planner-computed continuation**?

This is the follow-up to the five-task Plan Handoff × State Tracking development screen. It isolates the extra contribution of an explicit prior-plan status label. It does not introduce a new algorithm.

## Experimental contrast

Both arms receive exactly the same:

- original task request and checkpoint history;
- solver-supplied incumbent plan in the original history;
- common first action, exact arguments, and environment-specific native result;
- post-action typed state and current native tool definitions;
- complete minimum-cost continuation computed from the actual post-action typed state;
- model, decoding settings, maximum output tokens, and execution loop.

The only prompt difference is the single prior-plan status value at the end of the same post-action message:

| Environment | UNMARKED arm | ANNOTATED arm |
|---|---|---|
| RETAIN | \`UNSET\` | \`VALID\` |
| SWITCH | \`UNSET\` | \`STALE\` |

\`VALID\` means the remaining incumbent suffix is still minimum-cost from the actual post-action state. \`STALE\` means a strictly cheaper feasible continuation exists. Ties count as \`VALID\`.

The status is computed offline from the pinned native CostBench tool graph. It is an **oracle-derived diagnostic annotation**. Both arms already receive the same planner-computed continuation, so this experiment tests whether the extra explicit status annotation changes execution. It does not measure a deployable LLM-only method and does not establish a model-internal commitment mechanism.

## Task selection and common post-action state

Use the existing paired 50-task CostBench cohort, excluding only the five tasks used in the preceding Plan Handoff × State Tracking development screen. Tasks may overlap with other earlier CostBench diagnostics; this cohort is held out from the plan-handoff intervention, not globally unseen.

Select the first two eligible task IDs in lexicographic order within each of the five CostBench categories. Eligibility is fixed before any new provider call and requires:

1. the archived RETAIN and SWITCH trajectories both contain a successful first native action;
2. the first action name and exact argument string are identical in both paired environments; it may be on or off the incumbent plan;
3. the common action is nonterminal and the changed tool is not consumed by that common prefix;
4. replaying the exact common action in each paired native environment reproduces its archived result exactly;
5. after that common action, the unexecuted incumbent suffix (dropping its first step only if the common action was that step) remains feasible and minimum-cost in RETAIN, but strictly suboptimal in SWITCH.

This is a controlled post-action continuation cohort. It is **held out from the preceding plan-handoff intervention**, but may overlap with tasks used in other diagnostic studies; it is not a new or globally unseen CostBench dataset. Selection is conditioned on the archived baseline having taken the same first action in both paired environments; the scope of inference must reflect that restriction.

If two eligible tasks cannot be found in every category, or any exact replay/hash check fails, stop before provider calls. Do not relax the selection rule after inspecting eligibility counts.

## Frozen run matrix

- 10 base tasks (2 per category)
- 2 paired environments: RETAIN and SWITCH
- 2 status arms: UNMARKED and ANNOTATED
- 2 repetitions per task/environment/arm

Total: \`10 × 2 × 2 × 2 = 80\` full continuation trajectories.

Model settings: DeepSeek Flash, temperature 0, thinking disabled, 2,048 maximum output tokens per call. Each trajectory starts from an independently restored native tool registry and replays the same common first action before model continuation.

Operational hard cap for this follow-up: 1,200,000 provider tokens. The previous orphaned attempt remains conservatively reserved at 1,000,000 tokens; the completed 80-trajectory development screen used 725,465 provider tokens. The follow-up hard cap stays within the remaining previously approved envelope. No automatic retries are permitted.

## Outcomes and analysis

Primary outcomes:

- complete continuation optimality (\`continuation_regret = 0\` within tolerance);
- mean realized continuation regret;
- goal completion, reported separately from optimality.

Secondary outcomes:

- first post-checkpoint action Bellman regret;
- full-path regret including the fixed common-prefix loss;
- tool-call count, model-call count, provider tokens, elapsed time, invalid actions, and halt reason.

Compare ANNOTATED against UNMARKED within each task and environment. Report per-task paired differences and task-level means. The independent statistical unit is the base task (\`n=10\`); repetitions and RETAIN/SWITCH conditions are nested and paired, not independent samples. Report RETAIN and SWITCH separately as well as a balanced summary. Do not infer synergy or broad generalization from this two-arm experiment.

## Decision rules

- Annotation improves SWITCH without degrading RETAIN: evidence that explicit prior-plan status helps this controlled interface; confirm on a further task cohort before proposing a method.
- Annotation improves RETAIN but not SWITCH: the label may help preserve valid plans but does not resolve switching.
- Annotation improves SWITCH but harms RETAIN: the label is not sufficiently calibrated for selective replanning.
- No consistent task-level benefit: the full continuation itself likely explains the earlier B-arm gain; do not add a status module.
- Both arms remain suboptimal: inspect action-level loss and execution adherence; do not immediately design a new algorithm.
- Both arms are optimal: the status annotation is unnecessary in this task family; accept the simpler full-plan handoff result.

## Reproducibility and repository rules

- Keep all changes and results on the existing \`main\` branch. Do not create another branch.
- Pin CostBench to \`6424069f3f773ade076bcedbed302ed47cfb1837\`.
- Commit the selected task manifest before paid execution.
- Archive frozen requests, exact prompt hashes, responses, call-event journal, token ledger, and summary.
- The offline preparation and dry run must make zero provider calls.
- Any incomplete run is not a result. Do not replay a trial with an uncertain provider outcome; preserve the ledger and reconcile before any recovery.
