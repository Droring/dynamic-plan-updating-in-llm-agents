# Dynamic Plan Updating in LLM Agents

**An empirical study of plan retention, environment updates, and replanning failures.**

[中文说明](README_zh.md) · [Research mainline](research/plan_commitment_pilot/RESEARCH_MAINLINE.md) · [Experiment index](experiments/README.md) · [Manuscript workspace](paper/README.md) · [Related work](docs/RELATED_WORK.md) · [Reproducibility](docs/REPRODUCIBILITY.md) · [Algorithm provenance](docs/ALGORITHM_PROVENANCE_AND_CLEANUP.md)

> **Central question:** When an LLM Agent has formed and begun executing a plan, why can it fail to update that plan after new environment facts arrive? How can it correctly decide to RETAIN, REPAIR, or SWITCH based on current evidence?

## Project status

This repository studies how LLM Agents respond to updated environment facts and whether their decisions propagate into subsequent tool actions.

| Evidence package | Result | What it measures |
|---|---:|---|
| [Unified RETAIN/SWITCH study](experiments/paired_50/README.md) | **50 independent base tasks; 100 paired conditions** | Structured decisions and native first-action behavior |
| [Official native CostBench audit](experiments/native_80/README.md) | 80-task official run; static 70/80, dynamic 60/80; one task shared with the 50-task study | Final-answer robustness under static and dynamic execution |
| [Native plan-commitment and evidence-gate study](research/costbench_method_studies/plan_commitment_evidence_gate/README.md) | 67 event checkpoints from 80 candidates; 27 authentic prospective plans parsed | Agent-authored plan extraction and evidence-gated continuation |
| [Mechanism diagnosis](experiments/mechanism_diagnosis/README.md) | Reused development tasks and native traces | Observation, evidence invalidation, decision and action mismatches |
| [Intervention feasibility](experiments/interventions/README.md) | EDR and Action Guard prototypes | Exploratory intervention comparisons; no demonstrated advantage over simple fact updating |

The canonical paired dataset contains 50 distinct CostBench base tasks and 100 matched conditions: 50 RETAIN and 50 SWITCH. Each task contributes one matched pair, and each of the five CostBench categories contributes ten tasks. Historical fixture files are retained under the benchmark's provenance directory; the current study is accessed through one unified registry and builder.

In the structured decision evaluation, DeepSeek Flash achieved 48/50 RETAIN accuracy, 3/50 SWITCH accuracy and 1/50 paired accuracy. In the native execution evaluation, first-action accuracy was 48/50 on RETAIN and 2/50 on SWITCH; all 100 trajectories reached their goal. The two protocols measure different outcomes and are reported separately.

The official native 80-task audit found 13 tasks that changed from static-correct to dynamic-incorrect and 3 in the opposite direction. These counts measure final-answer robustness, not the cause of each failure.

## Research framing

After an environment update, an Agent may RETAIN a still-valid plan, REPAIR affected steps or dependencies, or SWITCH when the old plan is no longer appropriate. We distinguish failures in observing new facts, invalidating stale dependent evidence, evaluating alternatives, making an evidence-consistent decision, and executing or recovering from the selected action.

**Research focus:** reliable plan updating, state-aware decisions, and action-level recovery after environmental change. CostBench provides a controlled and reproducible tool environment.

## Start here

1. Read the [research mainline](research/plan_commitment_pilot/RESEARCH_MAINLINE.md).
2. Follow the [experiment index](experiments/README.md), starting with the [unified 50-task study](experiments/paired_50/README.md).
3. Review [related work](docs/RELATED_WORK.md) and the [manuscript outline](paper/README.md).
4. Check [reproducibility](docs/REPRODUCIBILITY.md), [limitations](docs/LIMITATIONS.md), and the [claim-evidence matrix](docs/CLAIM_EVIDENCE_MATRIX.md).

## Repository organization

The current tree is organized around a small set of CostBench evidence packages:

- `experiments/paired_50/`: primary 50-task paired benchmark.
- `experiments/native_80/`: official 80-task native robustness audit.
- `experiments/mechanism_diagnosis/` and `experiments/interventions/`: exploratory mechanism and intervention evidence.
- `research/`: plan-commitment audit, supporting native evidence and research interpretation.
- `docs/` and `paper/`: protocol, claims, limitations and manuscript structure.
- `scripts/` and `.github/workflows/`: current validation and reproducibility checks.

Original task inputs and provider responses needed to rebuild the 50-task benchmark remain under its provenance directory. The current branch presents the unified benchmark and its complementary CostBench evidence packages.
