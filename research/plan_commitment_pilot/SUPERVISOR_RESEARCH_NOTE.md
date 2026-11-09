# Research Note — Dynamic Plan Updating in LLM Agents

**For supervisor discussion | Unified 50-task paired study and complementary CostBench audits**

## Executive summary

This project studies how LLM Agents update multi-step tool plans after relevant environment facts change. The central question is whether updated facts propagate through observation, evidence refresh, decision-making and subsequent tool actions.

The primary paired benchmark is now one unified dataset of **50 independent CostBench base tasks**, each with matched RETAIN and SWITCH conditions (100 condition records). The benchmark is balanced across five CostBench categories. The 45 preserved source task pairs are merged into one source archive, with five newly generated tasks completing the canonical 50-task dataset. Raw construction records remain under provenance; the current study is generated, scored and reported through one registry.

The strongest result is a marked RETAIN/SWITCH asymmetry. DeepSeek Flash achieved 48/50 RETAIN and 3/50 SWITCH accuracy in the structured decision protocol. In a separate native CostBench execution protocol on the same 50 base tasks, first-action accuracy was 48/50 for RETAIN and 2/50 for SWITCH. All 100 native trajectories reached their goal, but the first action was identical across the two matched conditions in 48/50 task pairs.

These are controlled checkpoint results. The incumbent suffix is solver-derived and supplied at the checkpoint; the study does not establish that the Agent independently authored the original plan or that commitment to its own plan caused the observed behavior.

## 1. Research question

When an LLM Agent has formed and begun executing a multi-step tool plan, how should it respond when relevant environment facts change? When should it RETAIN a still-valid continuation, REPAIR affected steps or dependencies, or SWITCH to another feasible continuation?

The research focus is reliable plan updating and action-level recovery. CostBench price changes are used to construct controlled paired conditions; price optimization is not the intended research contribution.

## 2. Primary study: unified 50-task paired benchmark

The canonical dataset contains:
- 50 independent CostBench base tasks;
- 100 matched condition records: 50 RETAIN and 50 SWITCH;
- ten tasks in each of five CostBench categories;
- one frozen checkpoint per base task, shared by its matched conditions;
- 100 frozen structured model requests with request and checkpoint hashes.

### Structured decision results

| Measure | Result |
|---|---:|
| RETAIN accuracy | 48/50 (96%) |
| SWITCH accuracy | 3/50 (6%) |
| Paired accuracy | 1/50 (2%) |
| Balanced accuracy | 51% |
| Valid responses | 100/100 |

### Native CostBench execution results

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | 48/50 (96%) |
| SWITCH first-action accuracy | 2/50 (4%) |
| Overall first-action accuracy | 50% |
| Paired first-action accuracy | 1/50 (2%) |
| Same first-action decision in both conditions | 48/50 (96%) |
| Goal reached | 100/100 |
| Scored native trajectories | 100 |

The structured protocol measures the model's explicit decision label. The native protocol measures the first executed tool relative to the incumbent suffix. They are different outcomes and must be reported separately. Goal completion does not establish correct plan updating: an Agent can eventually reach the goal while retaining an inappropriate first action.

The canonical entry point is [the unified 50-task study](../../experiments/paired_50/README.md). The registry, frozen inputs, score files and native execution report are located under that package.

## 3. Complementary evidence

### Official native dynamic-robustness audit

The unmodified official CostBench Agent was audited on 80 tasks; one task (`Query00499`) is also included in the 50-task paired cohort. Static final-answer acceptance was 70/80 and dynamic acceptance was 60/80. Thirteen tasks changed from static-correct to dynamic-incorrect; three changed in the opposite direction. This demonstrates a dynamic robustness gap in the archived run, but does not attribute every degraded task to incorrect plan retention.

### Plan-commitment and evidence-gate audit

Across 80 candidate native tasks, 67 event checkpoints were replay-matched and 27 authentic prospective Agent-authored plans were parsed. This audit has a different unit and eligibility contract from the paired 50-task benchmark. It must not be added to the 50-task denominator.

### Mechanism and intervention studies

The mechanism diagnostics examine five observable stages:
1. Observation of the new environment fact.
2. Invalidation or refresh of dependent evidence based on old facts.
3. Evaluation of feasible alternatives.
4. Consistency between available evidence and the RETAIN/SWITCH decision.
5. Validity of the next action and recovery after execution.

Evidence-Dependency Refresh (EDR) and a pre-action Action Guard were implemented as exploratory prototypes. In the four-task development pilot, neither demonstrated an end-to-end advantage over a simple explicit old-to-new fact update. They are engineering baselines, not validated new algorithms.

## 4. Interpretation and contribution boundary

The current evidence supports three claims:
- Under the tested controlled paired checkpoint protocol, DeepSeek Flash exhibits a strong RETAIN response asymmetry.
- In the same 50-task cohort's native execution protocol, the first action often fails to distinguish RETAIN from SWITCH conditions, despite successful goal completion.
- The official 80-task audit independently shows lower final-answer acceptance under dynamic than static execution.

The evidence does not establish that all failures are caused by self-authored plan commitment, nor that the current intervention prototypes improve performance. The supplied incumbent is solver-derived, and the structured objective is a simulated tool-graph objective.

## 5. Reproducibility and repository structure

The project pins CostBench to commit `6424069f3f773ade076bcedbed302ed47cfb1837`. The unified benchmark has a single reader-facing entry point and a single dataset builder:

```bash
python experiments/paired_50/build_unified_dataset.py --check
python -m unittest scripts.test_unified_paired_dataset scripts.test_source_fixture_integrity -v
```

The structured evaluation uses the committed frozen requests and saved model responses. Native execution is separately documented under `experiments/paired_50/native_execution/`. Paid model calls are not required for offline integrity checks.

The merged source archive and raw construction records are retained only for provenance and regeneration. They are not presented as separate active studies. The official 80-task audit, 67-checkpoint audit and four-task intervention pilot remain separate evidence packages with their own denominators.

## 6. Next research milestone

The next scientific milestone is to establish a larger set of native cases with:
- a prospective plan genuinely authored by the Agent before the environment event;
- a replay-matched checkpoint and executed prefix;
- a verifiable RETAIN/SWITCH or REPAIR event pair at the same state;
- an independent semantic verifier for the updated user objective.

Only after a sufficient number of eligible independent tasks is established should a new method be compared against the simple explicit fact-update baseline.

## 7. Recommended supervisor discussion

**Is it worthwhile to develop state- and evidence-consistency-driven plan updating for tool-using Agents?** The current 50-task paired results provide a reproducible controlled signal, while the native audits identify the next requirement: connecting that signal to genuinely Agent-authored plans and semantically verified post-event objectives.
