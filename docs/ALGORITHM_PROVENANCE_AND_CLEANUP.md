# Algorithm and Experiment Provenance

This repository contains research conducted in the official CostBench environment. The current paper-facing contribution is an empirical study of plan updating and RETAIN/SWITCH behaviour, not a collection of independently validated algorithms.

## Current evidence and implementation status

| Component | Actual role | Current status |
|---|---|---|
| Official CostBench Agent | Unmodified benchmark baseline | Reproduced on 80 tasks; one task also appears in the primary 50-task cohort |
| Unified RETAIN/SWITCH benchmark | Controlled paired decision and native execution evaluation | 50 independent tasks; primary study |
| Native plan-commitment/evidence-gate audit | Checks whether a prospective Agent-authored plan can be recovered and validated at an observed event checkpoint | 67 event checkpoints; separate complementary study |
| Evidence-Dependency Refresh (EDR) | Prototype for identifying stale evidence after a fact update | Exploratory; no demonstrated end-to-end advantage |
| Action Guard | Prototype for checking action preconditions against current evidence | Exploratory; no demonstrated end-to-end advantage |

EDR and Action Guard are intervention feasibility studies, not validated algorithms. The repository does not claim a new method has outperformed the native baseline.

## Environment provenance

The primary environment is the official [CostBench](https://github.com/JiayuJeff/CostBench) tool-use benchmark, pinned to commit `6424069f3f773ade076bcedbed302ed47cfb1837`. The corresponding paper is Jiayu Liu et al., “CostBench: Evaluating Multi-Turn Cost-Optimal Planning and Adaptation in Dynamic Environments for LLM Tool-Use Agents,” ACL 2026 ([paper](https://aclanthology.org/2026.acl-long.584/)).

All retained empirical experiment packages in the current branch use CostBench data or its native execution harness. Non-CostBench experiments and superseded diagnostic implementations are not part of the current branch.

## Reporting rules

- Distinguish the 50-task paired benchmark, the 80-task official baseline and the 67-event plan-commitment audit.
- Do not add their denominators together.
- Describe solver-derived incumbent suffixes as supplied reference continuations, not Agent-authored plans.
- Attribute failures only to observable prompts, observations, state snapshots, tool calls and outcomes.
- Report exploratory interventions as exploratory, including negative results.
