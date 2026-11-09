# Experiment Index

The repository has one primary paired benchmark and a small set of complementary CostBench evidence packages. Each study keeps its own unit of analysis.

## Primary benchmark

| Study | Independent unit | Measurement |
|---|---:|---|
| [Unified RETAIN/SWITCH Decision and Native Execution Study](paired_50/README.md) | **50 base tasks** | 100 matched structured decisions and a separate 100-trajectory native execution protocol |

## Complementary CostBench evidence

| Study | Independent unit | Measurement |
|---|---:|---|
| [Official Native Dynamic-Robustness Audit](native_80/README.md) | 80 base tasks | Official Agent final-answer outcomes under static and dynamic execution |
| [Native Plan-Commitment and Evidence-Gate Study](../research/costbench_method_studies/plan_commitment_evidence_gate/README.md) | 67 event checkpoints from 80 candidates | Prospective Agent-authored plan extraction and evidence-gated continuation |
| [Mechanism Diagnosis](mechanism_diagnosis/README.md) | Reused development tasks and native traces | Observable failures in fact observation, evidence refresh, decision and action |
| [Intervention Feasibility](interventions/README.md) | Four development tasks with repeated arms | EDR and Action Guard feasibility; no demonstrated end-to-end advantage |

## Counting rules

The 50-task benchmark is the primary paired study. Its 100 conditions and 100 native trajectories are paired observations, not additional independent tasks. The 80-task audit and 67-checkpoint plan-commitment study are separate evidence packages with different denominators. Mechanism and intervention results reuse development tasks and are exploratory; they must not be pooled with the 50 independent tasks.

## Reproduction

Start with the [unified benchmark](paired_50/README.md), then use the [reproducibility guide](../docs/REPRODUCIBILITY.md), [claim-evidence matrix](../docs/CLAIM_EVIDENCE_MATRIX.md) and [limitations](../docs/LIMITATIONS.md). Original task inputs and model responses required to rebuild the primary benchmark are kept under its provenance directory.
