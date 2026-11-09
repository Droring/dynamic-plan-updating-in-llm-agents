# Official native CostBench static/dynamic audit (80 base tasks)

**Question:** Does the official CostBench Agent maintain task success when the environment is dynamically perturbed?

This 80-task cohort shares one base task (`Query00499`) with the canonical 50-task paired study. Report the two evidence packages separately; they are not fully task-disjoint.

| Outcome | Count |
|---|---:|
| Static final-answer correct | 70/80 |
| Dynamic final-answer correct | 60/80 |
| Static correct → dynamic incorrect | 13 |
| Static incorrect → dynamic correct | 3 |
| Replay-matched dynamic checkpoints | 67 |

The paired cross-tabulation is 57 correct in both conditions, 13 static-only correct, 3 dynamic-only correct, and 7 incorrect in both.

**Finding:** Native tool-execution accuracy decreased from 70/80 static to 60/80 dynamic. The 13 correct→incorrect transitions measure final-answer degradation; the RETAIN/SWITCH decision is analyzed in separate experiments.

**Action-level finding:** Among the 27 dynamic checkpoints with a uniquely recoverable Agent-authored pre-event plan, the original model's first post-event action followed that incumbent in 27/27 cases; 12/27 first actions differed from the current graph-optimal first action. See the [original-agent retention audit](../../research/costbench_method_studies/plan_commitment_evidence_gate/evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json) and its [reproduction script](../../research/costbench_method_studies/plan_commitment_evidence_gate/audit_original_agent_retention.py).

**Canonical records:** [Audited outcomes](../../research/plan_commitment_pilot/evidence/OFFICIAL_NATIVE_80_PAIRED_OUTCOMES.json), [audit script](../../research/plan_commitment_pilot/audit_official_native_80.py), [eligibility census](../../research/plan_commitment_pilot/evidence/ELIGIBILITY_CENSUS_80.json).
