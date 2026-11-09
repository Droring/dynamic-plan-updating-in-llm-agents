# Terminology

| Term | Meaning |
|---|---|
| **RETAIN** | Continue with the incumbent suffix when it remains valid under the updated environment. |
| **SWITCH** | Select a different continuation when the incumbent is no longer the correct choice under the benchmark objective. |
| **REPAIR** | Modify affected steps or dependencies while preserving reusable work. |
| **Base task** | One distinct CostBench scenario; the independent unit in the 50-task paired study. |
| **Matched pair** | RETAIN and SWITCH conditions derived from the same base task and frozen checkpoint. |
| **Condition** | One environment-update condition within a matched pair. |
| **Structured decision** | The model's explicit RETAIN/SWITCH response to a frozen request. |
| **Native first action** | The first tool actually executed by the official CostBench Agent after the event. |
| **Incumbent suffix** | The remaining reference continuation supplied at the controlled checkpoint; in the paired study it is solver-derived. |
| **Type-state checkpoint** | The recorded set of tool input/output types available at the decision point. |
| **Pair accuracy** | Fraction of base tasks for which both conditions in the matched pair are classified correctly. |
| **Balanced accuracy** | Mean of RETAIN and SWITCH class accuracies. |
| **Evidence invalidation** | Marking results or assumptions stale when they depend on facts that have changed. |
