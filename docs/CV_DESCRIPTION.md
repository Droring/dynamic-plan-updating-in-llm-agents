# Project description

**Dynamic Plan Updating in LLM Agents: An Empirical Study of RETAIN/SWITCH Behaviour**

A CostBench-based empirical study of whether an LLM Agent updates its continuation after the environment changes, and whether the updated decision is reflected in its next native tool action.

## CV bullets

- Built a unified, category-balanced benchmark of **50 independent CostBench tasks** with 100 matched RETAIN/SWITCH conditions, frozen requests, task manifests and reproducible scoring.
- Evaluated DeepSeek Flash under both structured decision and native tool-execution protocols. Structured paired accuracy was 1/50; native first-action paired accuracy was also 1/50, while all 100 native trajectories reached their goals.
- Audited the official CostBench Agent on an 80-task static/dynamic cohort, with one task shared with the primary paired study (70/80 static and 60/80 dynamic final answers accepted) and examined 67 event checkpoints for prospective Agent-authored plan evidence.
- Conducted exploratory mechanism and intervention studies on reused development traces, separating observable fact-update, evidence-refresh, decision and action failures.

The paired benchmark uses solver-derived incumbent suffixes supplied at controlled checkpoints. It does not establish that the Agent independently authored the initial plan. The mechanism probes and intervention pilots reuse development tasks and are not additional independent evaluations.

[Study protocol](STUDY_PROTOCOL.md) · [Results](RESULTS_SUMMARY.md) · [Evidence and limitations](LIMITATIONS.md)
