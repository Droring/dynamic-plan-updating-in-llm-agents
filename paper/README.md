# Manuscript workspace

Working title: **Dynamic Plan Updating Failures in LLM Agents: An Empirical Study of Plan Retention, Environment Updates, and Replanning Decisions**.

This workspace tracks a research manuscript grounded in the unified 50-task paired study and complementary native CostBench audits.

## Canonical evidence

1. **Unified RETAIN/SWITCH study:** 50 independent CostBench base tasks, 100 matched structured judgments and 100 native execution trajectories, reported as two distinct protocols. The task registry, frozen requests, scoring output, native traces and reproduction instructions are in [the paired 50-task study](../experiments/paired_50/README.md).
2. **Official native dynamic-robustness audit:** 80 tasks; 70/80 accepted static answers and 60/80 accepted dynamic answers. One task is shared with the primary 50-task cohort, with 13 correct-to-incorrect and 3 incorrect-to-correct paired transitions. See [the official native audit](../experiments/native_80/README.md).
3. **Plan-commitment/evidence-gate audit:** 67 replay-matched event checkpoints from 80 candidates; 27 authentic prospective plans parsed. This is a separate audit, not an addition to the 50-task benchmark.
4. **Mechanism and intervention studies:** development-task diagnostics and four-task fact-revision pilots. EDR and Action Guard did not demonstrate an end-to-end advantage over the explicit fact-update baseline.

## Key 50-task results

| Measure | Structured decision | Native first action |
|---|---:|---:|
| RETAIN accuracy | 48/50 (96%) | 48/50 (96%) |
| SWITCH accuracy | 3/50 (6%) | 2/50 (4%) |
| Paired accuracy | 1/50 (2%) | 1/50 (2%) |
| Goal reached | Not applicable | 100/100 |

The two protocols have different outcome definitions. The native agent reached every goal, while the first action was identical across matched conditions in 48/50 task pairs. The incumbent suffix is solver-derived and supplied at a controlled checkpoint; this is not a test of whether the Agent authored the original plan.

## Proposed paper structure

1. Introduction and motivation.
2. Related work: empirical agent failure analysis, recovery, replanning and temporal state updates.
3. Problem formulation: environment update and RETAIN / REPAIR / SWITCH.
4. Research questions and hypotheses.
5. Experimental setup, CostBench environment and validity criteria.
6. Unified paired results and official native robustness audit.
7. Mechanism diagnosis.
8. Intervention feasibility and negative findings.
9. Limitations and threats to validity.
10. Conclusion.

## Writing rules

- Use 50 independent base tasks as the primary paired-study denominator.
- Report 100 conditions, structured judgments and native trajectories as paired observations, not additional independent tasks.
- Keep structured decision labels and native first-action outcomes separate.
- Report the 80-task official audit and 67-checkpoint plan-commitment audit as distinct studies.
- Do not describe solver-derived incumbent suffixes as Agent-authored plans.
- Do not claim a validated new algorithm; the current interventions did not outperform the simple explicit fact-update baseline.

See [research mainline](../research/plan_commitment_pilot/RESEARCH_MAINLINE.md), [claim-evidence matrix](../docs/CLAIM_EVIDENCE_MATRIX.md), [limitations](../docs/LIMITATIONS.md), and [reproducibility](../docs/REPRODUCIBILITY.md).
