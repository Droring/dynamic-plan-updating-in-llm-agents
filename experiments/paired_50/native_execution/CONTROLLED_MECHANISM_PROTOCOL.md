# Controlled mechanism-discrimination protocol

## Purpose and current status

**Status: protocol specified; no new provider calls have been launched.**

This protocol tests whether making an environmental update explicit changes the **actual next tool action** in CostBench. It is a prospective, paired diagnostic rather than a new replanning algorithm. The primary contrast is a minimal current-state update versus an explicit old-to-new update. The experiment is not designed to infer hidden model thoughts from its explanations.

## Population and sampling

The sampling frame is the original official dynamic-run checkpoints with **Agent-authored pre-event plans**, not the solver-supplied plans in the 50-task cohort. The existing audit identifies 27 eligible authentic plans among 67 observed events. Its deterministic evidence gate classifies 22 RETAIN and 5 SWITCH with a fixed 0.25 switch penalty; these are reference labels, not model decisions.

**Primary minimum sample:** all five gate-SWITCH checkpoints and five gate-RETAIN checkpoints. Select the five RETAIN checkpoints by sorting their frozen query IDs lexicographically and taking the first five after excluding any task that overlaps the 50-task cohort. The same exclusion is applied to SWITCH checkpoints; if this leaves fewer than five eligible SWITCH checkpoints, use every eligible one and report the reduced sample rather than silently replacing it. Publish the exact query-ID manifest and exclusions **before** any provider calls. No outcome-dependent substitutions.

A checkpoint is eligible only if the pre-event plan and prefix can be recovered unambiguously, the original environment event and old/new tool fact can be reconstructed, and both arms can run from the identical native state. The independent solver must identify the reference first-action decision for both conditions. If any requirement fails, mark it in the eligibility manifest before running the experiment.

## Primary conditions

- **Minimal:** reproduce the original checkpoint with the current environment, the authentic Agent-authored incumbent, and a neutral statement that the environment has updated. Do not identify the changed tool or its previous value.
- **Explicit delta:** use exactly the same current environment, native state, tool definitions, incumbent plan, history, tool access, response format, and execution budget. Add only a factual statement naming the changed tool/property and its old and current values. Do not name a better path, suggest a tool, or provide an oracle-optimal value.

The minimal condition is the baseline. Both arms must expose the same **current** tool values through the tool interface; only the visibility of the *change event* differs. The explicit-delta arm necessarily has more historical information, so any difference identifies the effect of supplying change provenance, **not** a pure attention effect. Do not claim equal total information.

For all conditions, the current tool graph, types, dependency constraints, initial inventory, task, model version, temperature, tool-call limits, maximum output tokens, and scoring implementation are fixed. Save the exact serialized messages and available tool schema for each arm and verify byte equality after removing only the pre-registered event sentence.

## Optional follow-up contrasts (not part of the primary run)

- **Plan omitted:** remove the supplied plan but keep the executed prefix and all other facts; this tests the effect of a visible plan cue. It also changes prompt length and contextual guidance, so it is not a clean measure of internally formed commitment.
- **Explicit comparison request:** keep both current tool facts and incumbent, request comparison of feasible continuations without providing candidates. This jointly manipulates search instructions and reasoning budget; interpret separately from the explicit-delta effect.
- **Pre-commitment vs post-commitment:** requires genuinely matched histories at distinct plan-formation times. Existing checkpoints alone cannot isolate this contrast. Do not fabricate it by relabeling a supplied plan.

These contrasts require a separate decision to expand the study; do not bundle them into the primary experiment.

## Execution and randomization

For each selected task, run the two conditions from fresh independent model sessions, with temperature 0 and identical model configuration. Repeat each condition twice in a precommitted interleaved order, e.g. for each task use a seeded balanced permutation of Minimal/Explicit/Explicit/Minimal or Explicit/Minimal/Minimal/Explicit. Record the random seed and actual dispatch order. A full 10-task primary design uses **40 continuations**. No provider calls may begin until the manifest, prompt diffs, scorer checks and estimated call budget are reviewed and explicitly approved.

The original historical trajectory is observational evidence, not one of these randomized repetitions. Do not count reused prompts or deterministic gate replays as new independent trials.

## Scoring and outcome measures

Primary endpoint: **native first-action correctness** under the unchanged official solver/reference state and the frozen decision rule. A correct SWITCH requires the next action to belong to a current-optimal continuation; mere departure from the incumbent is insufficient. If multiple optimal first actions exist, count all of them using a fixed numerical tolerance and the same reference solver. A correct RETAIN requires a first action that preserves an optimal incumbent continuation, not simply a RETAIN label.

Secondary endpoints: exact incumbent first-action continuation, full suffix equality, total path optimality, valid tool arguments and prerequisites, goal reached, and decision stability across repetitions. Record per-task paired outcomes, not only pooled call-level percentages. Score unsuccessful and invalid calls without replacing them.

**Main contrast:** for each task, compute the explicit-minus-minimal difference in the fraction of correct first actions across the two repetitions. Report task-level differences separately for SWITCH and RETAIN, plus the number of tasks improved, unchanged, or worsened. Report the paired task-level mean and an uncertainty interval appropriate to the tiny sample; do not treat 40 calls as 40 independent tasks. With only five SWITCH tasks, prioritize individual paired trajectories over significance testing.

## Pre-run validation gates

1. Freeze query IDs, checkpoint hashes, original native traces, historical plan evidence, reference labels, and the exclusion log.
2. Validate the two prompts differ only by the allowed historical event statement; the current state and native tool definitions are identical.
3. Confirm both arms have the same next-action affordances and that old/new values are correct.
4. Check first-action oracle ties and feasibility with the pinned CostBench solver.
5. Lock model ID, provider parameters, repetition order, tool budgets, timeout handling and scoring code.
6. Run offline unit tests and a zero-provider-call dry run that reconstructs all selected checkpoints.
7. Obtain explicit approval for the estimated **40 paid model continuations** and any downstream tool execution.

Do not launch a partial paid run before these gates pass.

## Interpretation decision table

| Observation | Supports | Does not establish |
|---|---|---|
| Explicit delta improves SWITCH without reducing RETAIN | Change provenance matters for action selection | Whether the model previously noticed the change internally |
| Both conditions fail to SWITCH | Persistent failure under these two prompts | Plan anchoring versus deficient alternative search |
| Plan-omitted arm improves in later study | Supplied plan cue may matter | A causal self-authored commitment effect |
| Explicit comparison improves over delta alone | Search scaffolding may matter | Actual internal search or generalization to new tasks |
| Some RETAIN tasks become incorrect | Over-switching / instability | Successful adaptive replanning |
| No consistent difference across tasks | No replicated delta effect in this sample | Proof that change recognition is irrelevant |

## Reporting and stop rule

Stop after the pre-registered repetitions. Publish exact per-task actions and traces, prompt diffs, solver checks, failed calls, and all negative results. Do not add more tasks or revise prompts based on observed success without a new protocol. The study can identify whether explicit provenance changes actions; **it cannot alone causally separate plan anchoring, internal change detection, alternative search, and long-term commitment**. Any follow-up is selected based on the observed pattern and evaluated separately.
