# Counterfactual Proposal and Plan-Verification Gate

## Purpose

Test a **two-stage selective replanning** decision instead of appending more instructions to a single tool-call prompt. The prior 64-trial plan-preserving comparison pilot did not improve SWITCH; both prompt methods continued the incumbent in 16/16 SWITCH trials, and the added menu reduced RETAIN correctness once.

This new diagnostic uses the **already executed, plan-omitted C-arm first action** as a candidate proposal and separately asks the LLM to verify whether it deserves to replace the incumbent under the *current* environment. It retains the incumbent when no distinct candidate exists or verification does not produce a valid affirmative decision.

## Mechanism

1. **Candidate proposal:** Reuse the archived DeepSeek Flash C-arm first action (existing formal run [#42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176), 128-action archive). C was sampled **without seeing the incumbent**. It is not an oracle proposal or a computed optimal action.
2. **Plan-restoring verification:** If the archived C proposal differs from the incumbent, give a *new independent DeepSeek session* the original user request, completed prefix, current typed state, entire old plan, the candidate's first-action name, and complete current native tool definitions. Ask for JSON `KEEP` versus `ACCEPT`. Prompt contains no gold labels, oracle values or correct-action lists.
3. **Selective decision:** `ACCEPT` uses the C proposal; otherwise `KEEP` uses the known executable incumbent. Reuse archived successful C execution provenance; the gate does **not** yet carry out a new live tool call.
4. **Post-hoc scoring:** The independent pinned native solver evaluates the selected first action **after** model choice; reference values never enter the decision prompt.

### Frozen preflight

The 8 base tasks and 16 RETAIN/SWITCH checkpoints each have 2 archived repetitions, for **32 potential decisions**. Exactly **16/32** C first actions differed from the incumbent: 8 RETAIN cases, 8 SWITCH cases. The remaining 16 produce an automatic KEEP without an additional model call. Therefore, **16 new text-only DeepSeek verifier requests** are planned, capped at **250,000 provider tokens** (actual usage is recorded).

The 32 frozen decisions reuse earlier C responses; they are not 32 new independent tasks or new first-action generations. The eight tasks are the already-studied development cohort.

## Evaluation criteria

Primary: selected first-action optimality in RETAIN and SWITCH and their arithmetic mean (balanced accuracy). Compare with frozen original A (100% RETAIN, 12.5% SWITCH, balanced 56.25%) and C (50% RETAIN, 50% SWITCH, balanced 50%). Report the exact per-task, per-environment and per-repetition gate decisions, plus false ACCEPT and correct ACCEPT counts.

A **GO for actual new tool execution and held-out testing** requires RETAIN at least 14/16, SWITCH at least 8/16, balanced accuracy above 56.25%, no gold reference leaks in prompt, and no invalid or missing model response accepted as switching. Failure means stop this particular verification gate; do not adjust prompts on the same data after viewing outputs.

## Limitations

This is a retrospective candidate + prospective verifier pilot: the C first tool actions were generated in an earlier experiment and reused here, not newly sampled as part of one integrated agent session. Replayed first-action correctness does not establish complete-trajectory performance or deployment behavior. The gate text session and archived action session have different interface modalities. This controlled combination can test whether restoring plan context for comparison mitigates over-switching, but cannot prove an internal causal mechanism of plan commitment.

Protocol and evaluation are separate: the gate itself receives no oracle path or scores. The source candidate action may be optimal or suboptimal. The native solver provides an **external score** only.

## Reproduction

The run requires the pinned upstream CostBench checkout and downloaded `four-arm-deepseek-formal` artifact containing `responses.jsonl`:

```bash
python experiments/paired_50/native_execution/run_counterfactual_gate.py \
  --costbench-root ../CostBench --archive ./four-arm-formal
```

Default is an offline preflight. `--live` calls DeepSeek and writes raw serialized requests, candidate/decision records and score summaries.
