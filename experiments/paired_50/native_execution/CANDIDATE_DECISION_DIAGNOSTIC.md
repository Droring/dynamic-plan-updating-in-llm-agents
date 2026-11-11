# Candidate consideration and comparison diagnostic

**Stage:** Frozen offline design. **Provider calls:** 0. **New measured mechanism claims:** none.

## Motivation and evidence already available

The paired-50 native study reports 48/50 incumbent-following first actions in the SWITCH conditions, with 24/24 incumbent-following cases when an outside-plan tool becomes more attractive. The formal four-arm screen reports A/B SWITCH first-action correctness of 2/16, C of 8/16 and D of 9/16, while RETAIN correctness falls from 16/16 in A/B to 8/16 in C and 6/16 in D. A/B contain an externally supplied incumbent plan and C/D omit it. These are **observed action differences**, not observations of private model search or comparison.

The archived native candidate-availability audit confirms an available, type-feasible optimal first action in all 16 frozen environment checkpoints. Seven of the eight SWITCH-labelled checkpoints have a *suboptimal incumbent first action*; **Query00403 is SWITCH-labelled at the path level but its incumbent first action is still optimal.** It is a downstream-replanning case, not a first-action switching failure.

**Research question:** At an identical frozen checkpoint, can the model (i) mention a feasible non-incumbent candidate, (ii) correctly choose among explicitly provided feasible candidates under current tool facts, and (iii) implement its stated choice as a native tool call?

## Frozen population and selection

Reuse **only** the eight tasks in `FOUR_ARM_TASK_MANIFEST.json`. Within each task use exactly the two frozen RETAIN/SWITCH conditions, identical current tool interfaces, typed state, and the original solver-supplied incumbent suffix. Do not count the two original A/B/C/D repetitions as new independent tasks. The primary first-action diagnostic contains **15 eligible checkpoints** (8 RETAIN + 7 SWITCH with a suboptimal incumbent first action). Retain Query00403 as a separately reported **path-level diagnostic**, not as a SWITCH first-action error.

Primary strata are:
- **In-plan change:** Query00188, Query00550, Query00706 (SWITCH first-action eligible); Query00403 (path-level only).
- **Outside-plan change:** Query00347, Query00518, Query00685, Query00858 (SWITCH first-action eligible).
- Match every eligible SWITCH checkpoint to its own RETAIN condition. The baseline from the formal screen must be displayed per task and must not be resampled or pooled as independent observations.

## Diagnostics (three distinct endpoints)

**1. Candidate consideration (open-ended, no oracle hints).** Show the complete original checkpoint, typed state, available native tool interface, current tool values, and incumbent plan. Ask the model to output **up to three feasible next-tool names**, without providing the oracle candidate list or its reference values. Instruct it to include the incumbent when feasible and to identify any alternative it considers. Score whether it names at least one independently solver-verified optimal non-incumbent first action in the seven eligible SWITCH cases. Separately report tool existence, type feasibility, and whether the incumbent itself was included. An absent candidate in the output is only a **failure of explicit candidate reporting**; it is not proof that the model did not consider it privately.

**2. Candidate comparison (oracle-assisted diagnostic, no oracle values).** Starting from an independent fresh session and the *same checkpoint*, explicitly provide a fixed candidate menu containing the incumbent first action and every oracle-optimal first action, deduplicated. Supply **names only** and preserve the identical current tool definitions; do not disclose optimal values, scores, gold labels or recommended decisions. Randomize menu order in a reproducible, balanced way, including an order reversal. Ask for a single best first-action name. Score selection of any oracle-optimal action. Because the best candidate is supplied, this is **not deployable algorithm performance** and cannot establish that the model could have found that action unaided. In Query00403, this menu alone cannot identify the later changed-step failure.

**3. Choice-to-execution consistency.** In a third independent fresh session, provide exactly the same candidate menu and current tools and request a **native tool call** (not just a label). Score tool name correctness, type feasibility, successful native execution and consistency with the comparison-only choice, paired by task, condition and candidate order. Do not infer that a discrepancy proves any specific internal mechanism: the response format and action affordance differ between endpoints.

For a task where the incumbent and oracle-optimal first action are identical, do not label candidate menu effects as a change from RETAIN to SWITCH. Compare against *all* solver-optimal ties, with a fixed value tolerance `1e-6`.

## Implementation and control requirements

1. Lock the upstream CostBench revision `6424069f3f773ade076bcedbed302ed47cfb1837`, DeepSeek Flash configuration (temperature 0; thinking disabled), checkpoint hashes and the task manifest **before** model runs. Reconstruct state and first-action action-values through `run_four_arm_experiment.py::load_selected_trials` and `optimal_first_actions`.
2. For each endpoint use **fresh sessions**, no transcript carried from a previous endpoint. Candidate consideration must not receive reference actions; comparison and execution receive the identical menu and the exact same tool definitions, with only output modality different.
3. Record exact serialized prompts, tool schemas, menu order, response text, native tool call, checkpoint hash and reference solver outputs. Assert that no prompt includes `RETAIN`/`SWITCH` gold labels, oracle values or any instruction to pick a specific tool.
4. Freeze and log two repetitions and two balanced candidate orders per condition; calculate the budget **before** any paid calls. An offline dry run must reconstruct all 16 checkpoints and verify name/feasibility/type invariants, prompt diffs and candidate order.
5. Report first-action outcomes separately for the 7 eligible SWITCH tasks and 8 RETAIN tasks. Do not treat repetitions, candidate orderings or multiple endpoints as new independent tasks. Provide per-task tables before aggregates.
6. A failed/invalid response counts as a failure. No post-hoc replacement, rerun or prompt tuning on the evaluated tasks. A follow-up, if justified, must use untouched tasks and a newly declared evaluation protocol.

## How to interpret the evidence

| Open-ended candidate reported? | Correct choice with menu? | Correct native action with menu? | Narrow conclusion |
|---|---|---|---|
| No | Yes | Yes | Candidate *reporting/search scaffolding* is a plausible bottleneck; not proof of hidden search failure |
| Yes | No | No | Comparing supplied options under current facts is a plausible bottleneck |
| Yes | Yes | No | Choice-to-tool-call translation is a plausible bottleneck |
| No | No | No | These probes do not separate the bottlenecks |
| Yes | Yes | Yes | Under these aids, the tested checkpoint is resolvable; original plan-cue error remains real |

A complete, credible contribution requires showing **RETAIN as well as SWITCH** performance under identical conditions. A strategy that simply induces more switching but lowers RETAIN is not a validated improvement. The existing 16 full trajectories over two debug tasks are not substitutes for additional full-path tests on any eventual candidate policy.

## Current stop point

This document specifies *how to identify the stage of a failure*; it does not claim those stage outcomes have already been measured. Existing archived first actions cannot retroactively reveal a model's unobserved candidate set. Do not describe these diagnostics as executed experiments until request/response records and native execution traces exist.
