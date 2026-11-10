# Plan-Cue Dependence in Dynamic LLM Agent Replanning

**中文题目：动态环境下大语言模型智能体的计划保留偏向与重规划决策机制分析**

## Executive summary

This research pilot studies whether an LLM agent selects a valid but suboptimal incumbent plan after a dynamic environment change, and how showing the incumbent plan affects RETAIN versus SWITCH decisions. The principal finding is a **plan-cue trade-off**: showing a solver-supplied incumbent plan makes RETAIN first actions reliable but suppresses SWITCH in most tested checkpoints. Omitting the plan improves some SWITCH decisions but harms RETAIN, so plan removal alone is not a reliable replanning policy.

The work is an **experimental mechanism screen, not a new algorithm or a claim about internal psychological commitment**. It uses official native CostBench tools and a pinned upstream revision, frozen task checkpoints, a four-arm controlled prompt manipulation, task-level paired analysis, and limited full-trajectory continuation.

## Research question and hypotheses

**RQ:** When the environment changes after a plan is established, under what conditions does a model retain the incumbent first action despite an available better alternative, and what role does the visible incumbent-plan cue play?

- **H1: plan-cue dependence.** Showing an incumbent plan biases first-action selection toward that plan.
- **H2: current-fact reminder.** Explicitly repeating a changed tool's current cost improves SWITCH relative to otherwise identical prompts.
- **H3: asymmetric trade-off.** Removing the plan may improve SWITCH but also induce unnecessary deviations in RETAIN.
- **Open mechanism:** whether failures arise in candidate consideration, candidate comparison, or final selection is not identified by observing only selected actions.

The plan shown in this study was **solver-supplied**, not the agent's self-generated plan. The study therefore tests an externally presented plan cue, not the persistence of a self-authored commitment.

## Experimental design

Pinned upstream CostBench commit: `6424069f3f773ade076bcedbed302ed47cfb1837`. Model: `deepseek-flash`, temperature 0, thinking disabled.

Four arms:

| Arm | Incumbent plan shown | Current changed-tool cost repeated |
|---|---|---|
| A | Yes | No |
| B | Yes | Yes |
| C | No | No |
| D | No | Yes |

All four arms already include the complete current tool interface and current costs. The B/D manipulation is a **reminder/salience intervention**, not the provision of previously unavailable information.

Eight reused CostBench base tasks were evaluated in RETAIN and SWITCH environments, four arms, two repetitions: 8 × 2 × 4 × 2 = **128 native first-action evaluations**. The experimental unit for task-level inference is the **base task** (n = 8), not 128 independent samples. Query00403 is labelled SWITCH by its environment change but its incumbent **first** action remains optimal; it must not be counted as a first-action failure.

The pre-registered continuation subset uses Query00188 and Query00347 (2 tasks × 2 environments × 4 arms = **16 full paths**) and reuses the archived repetition-1 first action instead of resampling it.

## Data provenance and reproducibility

| Evidence | GitHub Actions run | Archived artifact |
|---|---|---|
| 16-request smoke test | [42658715641](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42658715641) | `four-arm-deepseek-smoke` |
| 128-request formal first-action screen | [42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176) | `four-arm-deepseek-formal`, ID 13697210404 |
| 16 full continuations | [42740440143](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42740440143) | `four-arm-continuations`, ID 13728279533 |

All 128 formal first actions were executed and scored successfully (zero API errors, zero invalid/missing tool calls, zero native execution errors). The formal screen recorded **714,046 tokens** against a 3,443,584-token cap. The continuation run reached the goal in all 16 trajectories and recorded **94,056 additional tokens** against a 500,000-token cap. The first actions in those continuations are already included in the formal run and **must not be counted as newly sampled actions**.

The offline audit found all 16 checkpoint-specific oracle-optimal first-action tools available and type-feasible. It also independently cross-checked shortest-path values on the two smoke tasks.

## Results I: first-action decision trade-off

| Environment | A plan | B plan + reminder | C no plan | D no plan + reminder |
|---|---:|---:|---:|---:|
| RETAIN optimal first action | 16/16 (100%) | 16/16 (100%) | 8/16 (50%) | 6/16 (37.5%) |
| SWITCH optimal first action | 2/16 (12.5%) | 2/16 (12.5%) | 8/16 (50%) | 9/16 (56.25%) |
| RETAIN mean first-action regret | 0 | 0 | 0.080 | 0.101875 |
| SWITCH mean first-action regret | 1.1375 | 1.1375 | 0.50125 | 0.42375 |

**Paired task-level results:**
- B versus A: no SWITCH or RETAIN task-level changes (0/8 improved, 0/8 worsened).
- C versus A: SWITCH improved in 3/8 tasks, unchanged in 5/8, worsened in 0/8; RETAIN worsened in 4/8 tasks, unchanged in 4/8.
- D versus B: SWITCH improved in 4/8 tasks, unchanged in 4/8, worsened in 0/8; RETAIN worsened in 5/8 tasks, unchanged in 3/8.

The model selected the incumbent first action in **all 32 A/B SWITCH observations**, including cases where the incumbent was suboptimal. Since the first action in Query00403 was still optimal, A/B's 2/16 SWITCH accuracy does not mean every SWITCH-labelled observation was an actual first-action failure.

**Interpretation:** Showing the incumbent plan has a strong observable association with incumbent-action selection in this controlled intervention. Removing it changes behavior in several tasks, improving SWITCH while harming RETAIN. Repeating the current changed-tool cost produces no measurable difference between A and B in this cohort. The correct target is **selective evidence-sensitive retention versus switching**, not simply reducing RETAIN frequency.

## Results II: full continuation

The two preselected debug tasks are both nonresponders to plan removal at the first SWITCH action, so they cannot establish that the formal-screen SWITCH gains persist to full paths.

| Condition | A | B | C | D |
|---|---:|---:|---:|---:|
| RETAIN goals reached | 2/2 | 2/2 | 2/2 | 2/2 |
| SWITCH goals reached | 2/2 | 2/2 | 2/2 | 2/2 |
| RETAIN mean full-path regret | 0 | 0 | 0.15 | 0.15 |
| SWITCH mean full-path regret | 1.30 | 1.30 | 1.45 | 1.45 |

**Query00188:** Every arm selected `Transportation_Search_to_Final_4Steps`, a composite tool that immediately reached the goal. No additional model calls were needed. RETAIN regret was 0; SWITCH regret was 1.30.

**Query00347:** Every arm began with `Search_Accommodation_Candidates`. A/B then used `Accommodation_Finish_from_Step1_3Steps` (one additional model call); C/D instead used `Accommodation_Refinement_Step1 -> Accommodation_Refinement_Step2 -> Select_Final_Accommodation` (three additional calls). This increased path regret from 0 to 0.30 in RETAIN and from 1.30 to 1.60 in SWITCH.

**Interpretation:** Plan cues can affect downstream action sequences even when the first action is identical. In these two full-path cases, removing the plan did not improve the outcome and sometimes made the path worse. Goal completion alone obscures these decision-quality differences.

## Evidence–claim matrix

| Claim | Evidence | Judgment |
|---|---|---|
| The agent often follows the incumbent action when shown a plan, including when it is suboptimal | 128 first-action requests, A/B SWITCH incumbent matches 32/32 | **Supported within cohort** |
| Removing the plan improves SWITCH first-action selection for some tasks | C–A improves 3/8; D–B improves 4/8 | **Supported within cohort** |
| Removing the plan also harms RETAIN | C–A worsens 4/8; D–B worsens 5/8 | **Supported within cohort** |
| Repeating the changed tool's current cost rescues decisions | A/B identical | **Not supported** |
| Better alternatives were unavailable or infeasible | 16/16 checkpoints pass candidate availability/type feasibility | **Contradicted by audit** |
| Plan omission improves complete trajectories | 16 paths over 2 nonresponder tasks | **Not supported in tested paths** |
| The failure is specifically due to candidate generation or ranking | Only selected tool actions observed | **Unresolved** |
| The model exhibits self-commitment or a psychological anchoring bias | Plan was solver-supplied | **Not tested** |
| A general-purpose new replanning algorithm is validated | No new policy implemented | **Not claimed** |

## Implications for method development

The next candidate method should preserve an incumbent plan as useful context while requiring evidence-sensitive comparison against feasible alternatives at the current state. Its design must distinguish:
1. **Candidate consideration:** Can the model name feasible incumbent and non-incumbent actions?
2. **Candidate evaluation:** Given a fixed candidate set, can it compare alternatives under current tool facts?
3. **Retention/switch calibration:** Can it retain the incumbent when optimal and switch when not, without overcorrecting?

A future diagnostic may present candidate sets and verified values as controlled aids, but any oracle-assisted test must be labelled as such and must not be marketed as a deployable method. Include both RETAIN and SWITCH cases, randomized candidate order, identical tool interfaces, and base-task-level reporting.

**Recommendation:** Conclude this pilot as a reproducible mechanism-screening result. Before proposing an algorithm, run a narrowly scoped candidate-consideration versus candidate-evaluation diagnostic on the existing checkpoints. Only if it reveals a reproducible, addressable failure mode should a selective-replanning mechanism be implemented and compared with baseline A, no-plan C, and simple decision rules on held-out tasks.

## Limitations and reviewer-facing disclosure

- Eight reused base tasks are a small, non-held-out cohort; two repetitions do not create 16 independent tasks.
- Full continuation covers only two preselected debug tasks, both first-action nonresponders in SWITCH.
- The plan cue is solver-supplied, not generated by the agent.
- The prompt manipulation changes the visible plan cue; it does not reveal private internal reasoning.
- The current-cost reminder is redundant with information already in the tool interface.
- Oracle minimum-cost continuation is a diagnostic reference; the study focuses on RETAIN/SWITCH decision correctness rather than claims of large cost savings.
- No population-level causal generalization or validated novel algorithm is claimed.

## Advisor-ready project summary (English)

**Dynamic Plan Updating in LLM Agents — Mechanism Study.** Investigated plan retention and adaptive replanning under environment changes using native CostBench and DeepSeek Flash. Designed a four-arm controlled prompt experiment (8 base tasks, 128 first-action evaluations) and a 16-trajectory continuation check. Found that exposing an incumbent plan preserved optimal RETAIN decisions (100%) but yielded low SWITCH first-action optimality (12.5%); removing the plan improved SWITCH (50–56.25%) while degrading RETAIN (37.5–50%). Verified candidate availability and reproduced task-level paired contrasts. Identified a plan-cue-dependent retention/switching trade-off that motivates evidence-sensitive replanning rather than unconditional plan removal.

## 面向导师的中文项目摘要

本项目研究动态环境变化后，大语言模型智能体对已有计划的保留与切换决策。基于 CostBench 官方工具环境与 DeepSeek Flash，设计四条件对照实验，在 8 个基础任务上完成 128 次首动作评估，并对 2 个预设任务完成 16 条完整轨迹续跑。结果显示：提供已有计划时，RETAIN 条件下的首动作最优率为 100%，但 SWITCH 条件下仅为 12.5%；移除计划后，SWITCH 最优率提高至 50%–56.25%，同时 RETAIN 降至 37.5%–50%。研究进一步核验了最优候选工具的可用性，并发现计划提示也会影响后续执行路径。结果揭示了计划保留与适应性切换之间的权衡，为后续研究基于当前证据的选择性重规划提供了可复现的实验基础。
