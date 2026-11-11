# Plan-Preserving Comparison Pilot — Native Results

## Outcome

**Decision: NO-GO for prompt-only plan-preserving comparison.** The pre-registered balanced-accuracy criterion in [BALANCED_REPLANNING_PROTOCOL.md](BALANCED_REPLANNING_PROTOCOL.md) was **not met**. Neither intervention improved SWITCH first-action correctness over the existing incumbent-visible baseline.

This negative result is important: explicit instruction to compare complete feasible continuations, even with an alphabetically sorted non-oracle list of all type-feasible first actions, did **not** change the model's SWITCH first action in any tested observation. A provided feasibility list caused one *incorrect* deviation under RETAIN.

## Provenance

- [Completed GitHub Actions #42959436017](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42959436017)
- [Raw frozen prompts, model responses, ledger and scores](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42959436017/artifacts/13828313347) (`balanced-replanning-pilot`, artifact ID `13828313347`)
- Execution SHA: `c86f92564e46ba793c34afd83a4a52ab7e267a89`
- 8 reused base tasks; RETAIN/SWITCH pair per task; 2 prompt conditions; 2 repetitions = **64/64** DeepSeek Flash model trials.
- 371,537 provider-reported tokens; 750,000 token limit; 0 API or native execution errors, no invalid tool calls.
- CostBench native revision `6424069f3f773ade076bcedbed302ed47cfb1837`; DeepSeek Flash; temperature 0; thinking disabled.
- Both methods retain the externally supplied incumbent plan. The `feasible_menu` intervention constructs its list using type availability, **not the reference solver or gold labels**.

## First-action comparison

| Method | RETAIN optimal | SWITCH optimal | Balanced accuracy | RETAIN incumbent following | SWITCH incumbent following |
|---|---:|---:|---:|---:|---:|
| Archived original A: plan visible | 16/16 (100%) | 2/16 (12.5%) | **56.25%** | 16/16 | 16/16 |
| Explicit continuation comparison | 16/16 (100%) | 2/16 (12.5%) | **56.25%** | 16/16 | 16/16 |
| Comparison + feasible names | 15/16 (93.75%) | 2/16 (12.5%) | **53.125%** | 15/16 | 16/16 |

All **32/32** SWITCH first actions in the two new methods followed the incumbent. The only SWITCH-labelled checkpoint with an optimal incumbent first action was **Query00403**, correctly counted as optimal at the first-action level in both repetitions of each method. These are **not** genuine improved first-action switching decisions.

The only new deviation was Query00706 / RETAIN / feasible_menu, repetition 1: the model selected `Dining_Refinement_Step1` instead of the optimal incumbent `Dining_Finish_from_Step1_3Steps`. Its repetition 2 retained correctly. This explains the 1/16 RETAIN deterioration.

## Per-task behavior

| Task | Explicit comparison RETAIN / SWITCH (correct out of 2) | Feasible-menu RETAIN / SWITCH (correct out of 2) |
|---|---|---|
| Query00188 | 2/2 / 0/2 | 2/2 / 0/2 |
| Query00347 | 2/2 / 0/2 | 2/2 / 0/2 |
| Query00403 | 2/2 / 2/2* | 2/2 / 2/2* |
| Query00518 | 2/2 / 0/2 | 2/2 / 0/2 |
| Query00550 | 2/2 / 0/2 | 2/2 / 0/2 |
| Query00685 | 2/2 / 0/2 | 2/2 / 0/2 |
| Query00706 | 2/2 / 0/2 | 1/2 / 0/2 |
| Query00858 | 2/2 / 0/2 | 2/2 / 0/2 |

*Query00403's first incumbent action remains optimal even in the SWITCH-labelled environment. This does not establish path-level replanning success.*

## Interpretation and methodological implications

The prior diagnostic found that on six of seven actual first-action SWITCH failures, the model could **explicitly report** an available oracle-optimal non-incumbent candidate. When given an oracle-quality menu, its text-only comparison was correct 6/14 and its tool action was correct 6/14. In contrast, **the present interventions give no oracle menu and retain the incumbent plan**; both leave the native first action unchanged in all SWITCH observations.

This evidence narrows the development strategy:
1. Repeating comparison instructions and listing feasible tool names do not sufficiently overcome incumbent-conditioned action persistence.
2. A method must do more than ask the same model to reason about a plan in a single tool-call prompt. The next stage should assess **a genuinely separate decision/verification step**, with an independent action recommendation followed by checked native execution, or an explicit evidence certificate for switching.
3. Feasible candidate lists are not automatically good candidate rankings; and an oracle-ranked menu is a diagnostic upper-bound aid, not an implementable non-oracle controller.
4. Any prospective method must preserve RETAIN and improve SWITCH under the same native protocol, then prove performance on *unseen* CostBench tasks and full paths.

The result does not imply that all explicit comparisons fail generally or that deeper internal comparison is impossible; it establishes that **these two frozen, prompt-only comparison variants failed under the evaluated checkpoints**.

## Decision and next experimental gate

Do **not** expand either prompt arm to the remaining 42 paired tasks. Freeze this negative result. For the next phase, implement a separate evidence-based candidate evaluation and an action-selection gate, without using the evaluation oracle inside the deployed decision policy. Validate that decision-stage output maps to a legal native action, preserve matched RETAIN/SWITCH tests, and compare against the original plan-visible A arm and simple fact-update baselines. Run a small development probe first; reserve untouched tasks for independent replication if it passes.

**This experiment did not validate a new replanning algorithm or improve balanced accuracy.**
