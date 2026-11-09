# Research Mainline — Dynamic Plan Updating in LLM Agents

## Research question

When an LLM Agent has formed a plan and begun executing it, how does it respond when relevant environment facts change? In particular, when should it RETAIN a still-valid continuation, and when should it SWITCH to a different feasible continuation? The broader objective is to understand how updated facts propagate from observation into decisions and actual tool actions.

CostBench is used as a controlled tool environment. Tool-price changes are an experimental mechanism for constructing matched RETAIN and SWITCH conditions, not the intended research contribution.

## Current primary evidence

### Unified 50-task paired study

The canonical structured dataset contains **50 independent CostBench base tasks and 100 matched conditions**: 50 RETAIN and 50 SWITCH. It is balanced across five CostBench categories (10 tasks each). Its first 45 task pairs are stored in one merged source archive, supplemented by five newly generated tasks. Readers and reproductions use the unified registry and builder.

The two conditions for each task share the same frozen checkpoint and differ in the controlled environment update. The frozen registry, 100 model requests, trial manifest and generation scripts are under [the unified 50-task study](../../experiments/paired_50/README.md).

**Structured decision results (DeepSeek Flash):**

| Measure | Result |
|---|---:|
| RETAIN accuracy | 48/50 (96%) |
| SWITCH accuracy | 3/50 (6%) |
| Paired accuracy | 1/50 (2%) |
| Balanced accuracy | 51% |

**Native CostBench execution results on the same 50-task cohort:**

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | 48/50 (96%) |
| SWITCH first-action accuracy | 2/50 (4%) |
| Overall first-action accuracy | 50% |
| Paired first-action accuracy | 1/50 (2%) |
| Same first-action decision in both conditions | 48/50 (96%) |
| Goal reached | 100/100 |

The structured label and native first-action outcome are different measurements and must remain separate. The native agent reached all goals, but its first action rarely changed across matched conditions. This shows why task completion alone is insufficient to assess whether an Agent updated its plan.

The incumbent suffix in this benchmark is solver-derived and supplied at a controlled checkpoint. The experiment measures decisions and observable execution relative to that incumbent; it does not establish that the Agent independently authored the original plan.

### Official native dynamic-robustness audit

The official CostBench Agent was evaluated on 80 tasks under static and dynamic conditions: 70/80 static and 60/80 dynamic final answers accepted. One task (`Query00499`) is also present in the 50-task paired cohort, so these evidence packages are not fully task-disjoint. Thirteen tasks changed from static-correct to dynamic-incorrect, while three changed in the opposite direction. This is evidence of a dynamic robustness gap, not proof that every degraded case was caused by incorrect plan retention.

### Plan-commitment and mechanism audits

The repository also retains the 67-checkpoint native plan-commitment/evidence-gate audit, fact-revision pilots, mechanism probes, and intervention feasibility tests. These are complementary or exploratory studies with their own denominators. They must not be added to the 50-task paired dataset or presented as additional independent tasks in that benchmark.

The four-task native fact-revision pilot found that the Agent could issue the corrected preference in its first post-event native action in all eight SWITCH continuations, while all eight RETAIN continuations preserved the existing preference. EDR and Action Guard prototypes did not demonstrate an end-to-end advantage over a simple explicit fact-delta prompt. These negative findings remain part of the research record.

## Failure analysis

The current evidence motivates examining five observable stages:

1. **Observation:** whether the new environment fact is actually received and represented.
2. **Evidence invalidation:** whether dependent assumptions, cached results or intermediate artifacts based on old facts are marked stale.
3. **Alternative evaluation:** whether the Agent considers currently feasible continuations rather than relying on the incumbent by default.
4. **Decision consistency:** whether RETAIN/SWITCH follows from the evidence already available to the Agent.
5. **Action and recovery:** whether the selected next action is valid, satisfies its prerequisites, and leads to a successful continuation.

The 50-task results establish a strong RETAIN response asymmetry under the tested controlled checkpoint protocol. They do not by themselves identify which of these stages causes the behavior, nor do they establish an Agent-authored commitment effect.

## Method-development status

Evidence-Dependency Refresh (EDR) and a bounded pre-action Action Guard were implemented and evaluated on reused development tasks. They provide engineering and diagnostic experience, but neither prototype demonstrated an end-to-end improvement over the simple explicit old-to-new fact update baseline. They are exploratory methods, not a validated proposed algorithm.

Future method design should follow a replicated action-level failure mechanism. Any method must preserve justified RETAIN decisions as well as trigger necessary SWITCH decisions, and must be evaluated against both a no-intervention baseline and a simple explicit fact-update baseline.

## Reading path

1. [Unified 50-task RETAIN/SWITCH study](../../experiments/paired_50/README.md)
2. [Native execution protocol and detailed results](../../experiments/paired_50/native_execution/README.md)
3. [Official 80-task native robustness audit](../../experiments/native_80/README.md)
4. [Mechanism diagnosis](../../experiments/mechanism_diagnosis/README.md)
5. [First method iteration](FIRST_METHOD_ITERATION.md)
6. [Supervisor research note](SUPERVISOR_RESEARCH_NOTE.md)
7. [Native plan-commitment and evidence-gate results](../costbench_method_studies/plan_commitment_evidence_gate/NATIVE_RESULTS.md)

## Repository and reporting rules

- Report the independent base-task count separately from conditions, trajectories, API calls, tool calls and workflow runs.
- The unified paired benchmark is 50 independent base tasks; 100 conditions are paired observations, not 100 independent tasks.
- Keep structured decisions and native first-action execution as distinct outcome measures.
- Keep the merged source archive and raw source records under `experiments/paired_50/provenance/source_records/source_archive/`; the canonical entry point is the unified 50-task registry and builder.
- Preserve raw provider responses, manifests, hashes and immutable audit records. Update reader-facing summaries and links without rewriting historical observations.
- Do not claim a validated new algorithm or causal plan-commitment effect from the current evidence.

## Current deliverable

A reproducible CostBench study with a unified 50-task paired dataset, a structured RETAIN/SWITCH decision evaluation, a native tool-execution evaluation, an 80-task official dynamic-robustness audit, mechanism diagnostics, and transparent negative intervention results. The strongest current empirical result is that DeepSeek Flash's first native action remained the same across both matched conditions in 48/50 task pairs, despite all 100 native trajectories reaching the goal.
