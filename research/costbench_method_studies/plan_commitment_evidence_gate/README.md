# Native Plan-Commitment Audit

This is a complementary development-only audit using the official CostBench Agent. It examines whether an Agent-authored plan written before an environment update can be recovered from the actual transcript and checked against the state observed at the event checkpoint.

## Population and protocol

The audit starts from the 80-task official native development population. A dynamic event was observed in 67 tasks; the remaining 13 ended before the event and are not post-event cases.

A plan is counted only when it was explicitly written by the Agent before the event, can be mapped unambiguously to public tools, agrees with the executed prefix, and has a valid remaining continuation from the recorded event state. A solver-generated reference path is never substituted for missing Agent-authored text. When no qualifying plan can be recovered, the audit records an explicit fallback rather than inventing a commitment.

The audit uses archived model responses and native traces. It does not constitute a new paid model rollout.

## Findings

- 27 of 67 event checkpoints contained a uniquely recoverable and executable prospective Agent-authored plan.
- Of those 27 plans, 22 were retained and 5 were replaced by a different continuation under the audit rule.
- The remaining 40 checkpoints used an explicit fallback because no qualifying plan was available.
- All 67 native continuations completed; 61/67 final answers were accepted, matching the archived full-replanning baseline.

These are descriptive results from the official CostBench development population. They do not establish that plan extraction improves general agent performance, and they do not identify the cause of the RETAIN asymmetry in the separate 50-task paired study.

## Evidence and implementation

- [Native results](NATIVE_RESULTS.md)
- [Per-task audit outcomes](evidence/NATIVE_AUDIT.json)
- [Complete native transcripts](evidence/native_event_cohort_67/RESULTS.json)
- [Replay-gate record](REPLAY_GATE.json)

Implementation files: `plan_memory.py`, `native_agent.py`, `run_native.py`, and `core.py`. The unit tests for plan-memory primitives are in [`scripts/test_plan_commitment_memory.py`](../../../scripts/test_plan_commitment_memory.py).

## Relationship to the main study

The 67 checkpoints are selected event observations from the 80-task official development population. They are not 67 additional independent tasks and must not be added to the 50-task paired benchmark.

The primary research question remains the RETAIN/SWITCH asymmetry observed in the unified 50-task study. This audit is supporting evidence about prospective plan availability and checkpoint observability, not the current proposed algorithm.
