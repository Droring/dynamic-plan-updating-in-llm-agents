# Full Continuation Results: Two-Task Pre-registered Check

## Provenance

- GitHub Actions run: [42740440143](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42740440143)
- Source formal first-action run: [42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176)
- Artifact: `four-arm-continuations` (ID 13728279533), SHA-256 `0a54eba4599be3e7e7084545e249fbb456258f7507cfa830b35f0dec08664480`
- Model: `deepseek-flash`; temperature 0; thinking disabled
- Design: 2 preselected base tasks x 2 environments x 4 arms = 16 full continuations; archived repetition-1 first actions are reused, not resampled.
- Completion: 16/16 reached goal; 16 additional provider calls; 94,056 additional tokens (500,000-token hard cap). The archived first-action requests used 88,968 tokens separately.

## Aggregate outcomes

| Environment | Arm A | Arm B | Arm C | Arm D |
|---|---:|---:|---:|---:|
| RETAIN goal success | 2/2 | 2/2 | 2/2 | 2/2 |
| SWITCH goal success | 2/2 | 2/2 | 2/2 | 2/2 |
| RETAIN mean completed-path regret | 0.00 | 0.00 | 0.15 | 0.15 |
| SWITCH mean completed-path regret | 1.30 | 1.30 | 1.45 | 1.45 |

All trajectories reached their goal. The distinction is full-path optimality, not task success.

## Exact trajectories

### Query00188 (transportation)

In RETAIN and SWITCH, all four arms followed:
`Transportation_Search_to_Final_4Steps`

The single composite first tool already reached the goal, so **zero additional model calls** were required for each of these eight trajectories. RETAIN regret = 0; SWITCH regret = 1.30.

### Query00347 (accommodation)

All four arms chose `Search_Accommodation_Candidates` as the first action in both environments. The subsequent paths differed:

- A and B: `Search_Accommodation_Candidates -> Accommodation_Finish_from_Step1_3Steps`; one additional model call per trajectory; RETAIN regret = 0, SWITCH regret = 1.30.
- C and D: `Search_Accommodation_Candidates -> Accommodation_Refinement_Step1 -> Accommodation_Refinement_Step2 -> Select_Final_Accommodation`; three additional model calls per trajectory; RETAIN regret = 0.30, SWITCH regret = 1.60.

These results show that plan omission can change **later** actions even when the first action is identical. In Query00347 it changed the continuation to a longer, less optimal path in both environment conditions.

## Mechanism interpretation

The 8-task, 128-request first-action screen showed a plan-cue trade-off: plan omission improved SWITCH decisions for some tasks while harming RETAIN decisions. The 2-task full continuation check does not establish any full-path gain; in its selected cases it shows unchanged or worsened path regret after plan omission. The difference is expected because the two pre-registered tasks were both first-action nonresponders in SWITCH.

Do not report 16 independent tasks: this is a paired two-task diagnostic. Do not report a new 16-call first-action experiment: all first actions are inherited from the formal screen.

The stronger supported conclusion is that the plan cue affects both **initial selection** (in the broader eight-task screen) and **subsequent path choice** (Query00347). The current data do not isolate whether the model's failure is in candidate generation, value comparison, or final selection. That distinction requires a separate diagnostic.

## Next step

Complete the mechanism synthesis with task-level contrasts and clearly separate three claims: (1) the eight-task first-action plan-cue trade-off; (2) the two-task full-path outcome; (3) the still-unidentified internal selection mechanism. No additional paid experiments are necessary to report these findings as a research pilot.
