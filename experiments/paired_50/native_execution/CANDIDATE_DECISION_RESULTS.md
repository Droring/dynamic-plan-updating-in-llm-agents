# Candidate Consideration, Comparison and Action Diagnostic — Results

## Status and provenance

**Completed:** one real DeepSeek Flash execution on the eight already studied CostBench tasks; 75/75 diagnostic requests successfully answered. Pinned upstream CostBench: `6424069f3f773ade076bcedbed302ed47cfb1837`. Model configuration: temperature 0, thinking disabled.

- [GitHub Actions run #42956148699](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42956148699) — successful
- [Raw archived requests, responses and scoring summary](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42956148699/artifacts/13827162265) — `candidate-decision-results`, artifact ID `13827162265`
- 75 requests; 415,040 provider-reported tokens against a hard cap of 600,000; 0 API errors.
- Eight reused base tasks, 16 RETAIN/SWITCH checkpoints, 15 eligible first-action diagnostic checkpoints (8 RETAIN + 7 SWITCH). `Query00403` is SWITCH at the **path** level but its incumbent **first action remains optimal**; it was excluded from the first-action SWITCH denominator.
- The candidate menu contains the incumbent first action and all independently solver-optimal first-action **names**, without optimality scores or labels. Both candidate-menu orders are tested. These are diagnostic interventions, not performance of an agent that independently constructs an oracle-quality menu.
- The text-only prompts received read-only copies of the current tool schemas; the action endpoint received callable current native tools. Each endpoint used a fresh model session, not a single chain-of-thought transcript.

## Primary outcomes

| Condition | Explicit consideration: reports an optimal candidate | Provided-menu comparison: selects optimal | Native provided-menu execution: executes optimal |
|---|---:|---:|---:|
| RETAIN | 8/8 (100%) | 16/16 (100%) | 16/16 (100%) |
| SWITCH, suboptimal incumbent first action | 6/7 (85.7%) | 6/14 (42.9%) | 6/14 (42.9%) |

In the SWITCH consideration endpoint, **6/7** tasks explicitly named at least one feasible oracle-optimal **non-incumbent** action among up to three reported candidate tools. All 30 native execution tool calls succeeded. No API errors were recorded.

Comparison-only choice and independent native tool choice matched for **28/30** paired task/environment/order cells. The remaining two discrepancies both occurred on `Query00550` SWITCH, where the text-only and tool-call endpoints selected opposite menu choices under both candidate-order variants. Their marginal optimality totals happen to match, but **these are separate model sessions**, not demonstrated execution of an earlier stated decision.

### Task-level SWITCH breakdown

| Task | Changed tool in incumbent? | Optimal non-incumbent explicitly reported? | Comparison correct | Native action correct | Notes |
|---|---|---:|---:|---:|---|
| Query00188 | Yes | Yes | 1/2 | 1/2 | Choice changes with reversed menu ordering |
| Query00347 | No | Yes | 0/2 | 0/2 | Available best action is named, but old first action is chosen |
| Query00518 | No | Yes | 0/2 | 0/2 | Available best action is named, but old first action is chosen |
| Query00550 | Yes | Yes | 1/2 | 1/2 | Comparison/action disagree across the two orders |
| Query00685 | No | Yes | 2/2 | 2/2 | Candidate menu enables correct choice and execution |
| Query00706 | Yes | Yes | 2/2 | 2/2 | Candidate menu enables correct choice and execution |
| Query00858 | No | **No** | 0/2 | 0/2 | Free proposal misses the best candidate; the given menu still fails |

The two successful-choice tasks are `Query00685` and `Query00706`, two partially correct tasks are `Query00188` and `Query00550`, and three failed-choice tasks are `Query00347`, `Query00518`, and `Query00858`. These are **seven independent base tasks**, not fourteen independent samples; the two menu orders are paired repeats.

## What this identifies

1. **Pure candidate-unavailability does not explain the failure.** The independent native solver confirms the oracle-optimal actions exist and are feasible. For six of seven SWITCH tasks the model also explicitly **reports** an optimal alternative when asked.
2. **Candidate comparison and final selection are a plausible, directly observable bottleneck under the supplied-menu condition.** Providing a menu containing the correct action still yields 6/14 SWITCH correctness, while RETAIN remains 16/16.
3. **Choice-to-tool-call translation is not the dominant observed issue in this protocol.** The two independently elicited choice endpoints agree in 28/30 cells; all 30 tool executions succeed. A disagreement across fresh sessions is not proof of an internal execution error.
4. **Failure is not uniform.** Two SWITCH tasks respond fully to supplied candidates, two are unstable under menu reversal, and three continue to choose suboptimal incumbent actions. The task and interface context matter.

## Critical interpretation limits

- The three endpoints use different prompts, response modalities, and fresh sessions. Thus their marginal accuracy numbers **cannot be used as a causal breakdown of the model's internal search, comparison, and action-selection process**.
- A candidate's appearance in a requested JSON list measures **reported candidate availability**, not a private, exhaustive candidate-search trace. Conversely, absent reporting does not prove it was not considered.
- The comparison menu uses the oracle-optimal action name, which is privileged diagnostic assistance; its 42.9% SWITCH score is **not** a deployment-ready intervention result.
- All eight tasks were already used in the four-arm mechanism screen. This is an **in-sample, exploratory mechanism localization test**; no held-out model validation has been conducted.
- Candidate-menu ordering is balanced only across two reversed lists. In `Query00188` the choice changes between them; order sensitivity remains a possible confound.
- No new general-purpose replanning policy and no improvement in complete trajectories are established by these 75 calls.

## Consequence for the next study

The evidence favors testing **evidence-conditioned comparison of feasible incumbent and non-incumbent continuations**, rather than relying solely on plan omission or on supplying more candidate names. In the next *method development* phase, keep the incumbent plan visible and test whether an explicit comparison procedure under current facts improves SWITCH **without damaging RETAIN**. Use a non-oracle candidate generator for deployable variants, compare against original-plan, no-plan, menu-only and simple fact-update baselines, and validate on untouched tasks before making an algorithm-performance claim.

**Decision:** Mechanism-screening diagnostic completed; proceed to narrowly scoped method design only after its comparison procedure and controls are specified. Do not describe the above as a validated algorithm.
