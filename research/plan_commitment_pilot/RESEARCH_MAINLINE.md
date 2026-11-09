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

### Official native dynamic-robustness and original-plan audit

The official CostBench Agent was evaluated on 80 tasks under static and dynamic conditions: 70/80 static and 60/80 dynamic final answers accepted. One task (`Query00499`) is also present in the 50-task paired cohort, so these evidence packages are not fully task-disjoint. Thirteen tasks changed from static-correct to dynamic-incorrect, while three changed in the opposite direction.

A separate audit of the original raw dynamic runs recovered **27** Agent-authored pre-event plans from the 67 observed event checkpoints. The original pre-event executed prefix matched the written plan in 27/27 cases. The actual first post-event model action followed the incumbent in **27/27** cases; it matched the current graph-optimal first action in 15/27 and differed in 12/27. Under the deterministic evidence gate's 0.25 switch penalty, five cases were classified as SWITCH; the original model still followed the incumbent first action in all five and matched the optimal first action in none. All 27 reached the goal, while 24/27 final answers were accepted.

The gate's 22 RETAIN / 5 SWITCH counts are symbolic gate outputs, not model decisions. The 27/27 result is the separate extraction of actual post-event tool calls from the original official conversation histories. See the [reproducible audit](../costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json).

### Plan-commitment and mechanism audits

The repository also retains the 67-checkpoint native plan-commitment/evidence-gate audit, fact-revision pilots, mechanism probes, and intervention feasibility tests. These are complementary or exploratory studies with their own denominators. They must not be added to the 50-task paired dataset or presented as additional independent tasks in that benchmark.

The four-task native fact-salience audit found that, on SWITCH cases, first-action correctness increased from 2/4 with a minimal current-value update to 4/4 with an explicit old-to-new correction. RETAIN preference decisions were 4/4 in both conditions; one explicit-update RETAIN arm made an invalid tool call. A separate four-task fact-link control found 2/4 for minimal wording and 4/4 for both simple change wording and an added old-result-dependency statement; the extra dependency statement provided no further gain. EDR and Action Guard did not demonstrate an incremental advantage over the simple explicit-delta prompt. These are small development probes, not confirmatory estimates.

## Failure analysis

The current evidence motivates examining five observable stages:

1. **Observation:** whether the new environment fact is actually received and represented.
2. **Evidence invalidation:** whether dependent assumptions, cached results or intermediate artifacts based on old facts are marked stale.
3. **Alternative evaluation:** whether the Agent considers currently feasible continuations rather than relying on the incumbent by default.
4. **Decision consistency:** whether RETAIN/SWITCH follows from the evidence already available to the Agent.
5. **Action and recovery:** whether the selected next action is valid, satisfies its prerequisites, and leads to a successful continuation.

The 50-task results establish a strong RETAIN response asymmetry under a solver-supplied incumbent protocol. The original native-plan audit independently finds the same first-action persistence when the incumbent was authored by the Agent. Neither result identifies which observable stage causes the behavior.

## Method-development status

Evidence-Dependency Refresh (EDR) and a bounded pre-action Action Guard were implemented and evaluated on reused development tasks. They provide engineering and diagnostic experience, but neither prototype demonstrated an end-to-end improvement over the simple explicit old-to-new fact update baseline. They are exploratory methods, not a validated proposed algorithm.

Future method design should follow a replicated action-level failure mechanism. Any method must preserve justified RETAIN decisions as well as trigger necessary SWITCH decisions, and must be evaluated against both a no-intervention baseline and a simple explicit fact-update baseline.

## Reading path

1. [Unified 50-task RETAIN/SWITCH study](../../experiments/paired_50/README.md)
2. [Native execution protocol and detailed results](../../experiments/paired_50/native_execution/README.md)
3. [Official 80-task native robustness audit](../../experiments/native_80/README.md)
4. [Mechanism diagnosis](../../experiments/mechanism_diagnosis/README.md)
5. [Original native-agent retention audit](../costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json)
6. [Paired-cohort mechanism analysis](../../experiments/paired_50/native_execution/MECHANISM_ANALYSIS.md)
7. [First method iteration](FIRST_METHOD_ITERATION.md)
8. [Supervisor research note](SUPERVISOR_RESEARCH_NOTE.md)
9. [Native plan-commitment and evidence-gate results](../costbench_method_studies/plan_commitment_evidence_gate/NATIVE_RESULTS.md)

## Repository and reporting rules

- Report the independent base-task count separately from conditions, trajectories, API calls, tool calls and workflow runs.
- The unified paired benchmark is 50 independent base tasks; 100 conditions are paired observations, not 100 independent tasks.
- Keep structured decisions and native first-action execution as distinct outcome measures.
- Keep the merged source archive and raw source records under `experiments/paired_50/provenance/source_records/source_archive/`; the canonical entry point is the unified 50-task registry and builder.
- Preserve raw provider responses, manifests, hashes and immutable audit records. Update reader-facing summaries and links without rewriting historical observations.
- Do not claim a validated new algorithm or causal plan-commitment effect from the current evidence.

## Current deliverable

A reproducible CostBench study with a unified 50-task paired dataset, a structured RETAIN/SWITCH decision evaluation, a native tool-execution evaluation, an 80-task official dynamic-robustness audit, mechanism diagnostics, and transparent negative intervention results. The strongest direct plan-retention result is that, in 27 original native trajectories with recoverable Agent-authored plans, the first post-event model action followed the incumbent in 27/27 cases; in the five cases where the independent gate selected SWITCH, the model still followed the incumbent in 5/5. The separate 50-task paired study reproduces strong incumbent persistence under a solver-supplied plan.
