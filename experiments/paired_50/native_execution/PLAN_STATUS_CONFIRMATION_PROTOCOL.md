# Plan-Status Annotation Confirmation

## Research question

At the frozen CostBench checkpoint immediately after the environment update, does explicitly annotating the validity of the previously supplied plan improve complete continuation execution **beyond providing the same complete planner-computed continuation**?

This is a focused follow-up to the five-task Plan Handoff × State Tracking development screen. It isolates the incremental effect of an explicit prior-plan status label. It does not introduce a new algorithm.

## Final design and rationale

An initial post-action design required the archived baseline to have executed the same successful incumbent-first action, with identical arguments, in both RETAIN and SWITCH. The offline feasibility screen found only seven eligible tasks across four categories and no eligible accommodation task. That could not support the predeclared balanced ten-task cohort. No provider calls were made under that design.

The final design therefore compares both status arms from the **same original frozen checkpoint**, without conditioning task inclusion on the archived model's first action. This is closer to the decision point immediately after the environment update and preserves the key causal contrast: within each task/environment cell, the only prompt manipulation is the explicit status label. It avoids relaxing task eligibility after seeing the failed post-action screen.

## Experimental contrast

Both arms receive exactly the same:

- original task request and frozen typed checkpoint;
- original pre-update incumbent plan;
- current environment's native tool definitions and costs;
- complete feasible minimum-cost continuation computed by the graph planner from that checkpoint;
- model, decoding settings, maximum output tokens, and native execution loop.

The only prompt difference is the single prior-plan status value at the end of the planner message:

| Environment | UNMARKED arm | ANNOTATED arm |
|---|---|---|
| RETAIN | \`UNSET\` | \`VALID\` |
| SWITCH | \`UNSET\` | \`STALE\` |

\`VALID\` means the incumbent suffix remains minimum-cost from the current checkpoint. \`STALE\` means it remains feasible but is strictly more expensive than a minimum-cost continuation. Ties count as \`VALID\`. \`UNSET\` means no validity annotation is supplied.

The status is computed offline from the pinned native CostBench tool graph. It is an **oracle-derived diagnostic annotation**. Both arms already receive the same planner-computed continuation, so this experiment tests whether the extra explicit status label changes execution. It does not measure a deployable LLM-only method and does not establish a model-internal commitment mechanism.

## Task selection

Use the existing paired 50-task CostBench cohort, excluding tasks already used in:

- the four-arm mechanism screen;
- the bounded-verifier confirmation;
- the five-task plan-handoff development screen.

Select the first two eligible task IDs in lexicographic order within each of the five CostBench categories. Eligibility is determined offline and requires:

1. both RETAIN and SWITCH frozen checkpoints reconstruct successfully at the pinned upstream revision;
2. the paired checkpoints have identical checkpoint hashes, prefixes, and incumbent plans;
3. the incumbent suffix is feasible from each checkpoint;
4. an independently reconstructed native typed-graph optimum confirms that the incumbent is minimum-cost in RETAIN and strictly suboptimal in SWITCH;
5. the native solver audit and independent graph-planner values agree within tolerance.

The cohort is held out from the prior mechanism interventions, but it is **not a new or unseen CostBench dataset**. Selection is conditioned on the existing paired benchmark construction; the scope of inference must reflect that.

If two eligible tasks cannot be found in every category, or any checkpoint/hash/oracle consistency check fails, stop before provider calls. Do not relax the selection rule after inspecting eligibility counts.

## Frozen run matrix

- 10 base tasks (2 per category)
- 2 paired environments: RETAIN and SWITCH
- 2 status arms: UNMARKED and ANNOTATED
- 2 repetitions per task/environment/arm

Total: \`10 × 2 × 2 × 2 = 80\` full continuation trajectories.

Model settings: DeepSeek Flash, temperature 0, thinking disabled, 2,048 maximum output tokens per call. Each trajectory starts from an independently deep-copied native tool registry and the exact frozen typed checkpoint.

Operational hard cap for this follow-up: 1,200,000 provider tokens. The previous orphaned attempt remains conservatively reserved at 1,000,000 tokens; the completed 80-trajectory development screen used 725,465 provider tokens. This follow-up cap remains within the previously approved aggregate envelope. No automatic retries are permitted.

## Outcomes and analysis

Primary outcomes:

- complete continuation optimality (\`continuation_regret = 0\` within tolerance);
- mean realized continuation regret;
- goal completion, reported separately from optimality.

Secondary outcomes:

- first-action and subsequent-step Bellman regret;
- updated-plan and incumbent-plan adherence;
- tool-call count, model-call count, provider tokens, elapsed time, invalid actions, and halt reason.

Compare ANNOTATED against UNMARKED within each task and environment. Report per-task paired differences and task-level means. The independent statistical unit is the base task (\`n=10\`); repetitions and RETAIN/SWITCH conditions are nested and paired, not independent samples. Report RETAIN and SWITCH separately as well as a balanced summary. Do not infer broad generalization or synergy from this two-arm experiment.

## Decision rules

- Annotation improves SWITCH without degrading RETAIN: evidence that explicit prior-plan status helps this controlled interface; confirm on a further task cohort before proposing a method.
- Annotation improves RETAIN but not SWITCH: the label may help preserve valid plans but does not resolve switching.
- Annotation improves SWITCH but harms RETAIN: the label is not sufficiently calibrated for selective replanning.
- No consistent task-level benefit: the full continuation itself likely explains the earlier plan-handoff gain; do not add a status module.
- Both arms remain suboptimal: inspect action-level loss and execution adherence; do not immediately design a new algorithm.
- Both arms are optimal: the status annotation is unnecessary in this task family; accept the simpler full-plan handoff result.

## Reproducibility

- Keep all changes and results on the existing \`main\` branch. Do not create another branch.
- Pin CostBench to \`6424069f3f773ade076bcedbed302ed47cfb1837\`.
- Commit the selected task manifest before paid execution.
- Archive frozen requests, exact prompt hashes, responses, call-event journal, token ledger, and summary.
- Offline preparation and dry run must make zero provider calls.
- Any incomplete run is not a result. Do not replay a trial with an uncertain provider outcome; preserve the ledger and reconcile before any recovery.
