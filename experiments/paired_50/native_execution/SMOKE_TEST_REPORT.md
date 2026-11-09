# Four-Arm DeepSeek Smoke-Test Report

## Run provenance

- Repository: `Droring/dynamic-plan-updating-in-llm-agents`
- Branch: `research/four-arm-mechanism-screen`
- GitHub Actions run: [42658715641](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42658715641)
- Run commit: `e0d0427590d169fe7d61bba6026c1685db6bd525`
- Model: `deepseek-flash`
- Thinking: disabled
- Temperature: 0
- Planned / completed requests: 16 / 16
- API retries: none
- Token hard cap: 500,000
- Accounted tokens: 88,968 (17.79% of cap)
- Outcome: successful; all 16 first actions were natively executed and scored.

The workflow uploaded the raw `requests.jsonl`, `responses.jsonl`, `summary.json`, and `ledger.json` as the `four-arm-deepseek-smoke` artifact. The artifact is retained by GitHub Actions; this report does not replace those raw records.

## Results

Each cell has two observations: one from each of the two selected base tasks. The two tasks are Query00188 and Query00347. Each task was evaluated in both RETAIN and SWITCH environments, with one request per prompt arm.

| Environment | Arm | Optimal first actions | Valid executions | Mean first-action regret | Incumbent first actions |
|---|---:|---:|---:|---:|---:|
| RETAIN | A | 2/2 | 2/2 | 0.00 | 2/2 |
| RETAIN | B | 2/2 | 2/2 | 0.00 | 2/2 |
| RETAIN | C | 2/2 | 2/2 | 0.00 | 2/2 |
| RETAIN | D | 2/2 | 2/2 | 0.00 | 2/2 |
| SWITCH | A | 0/2 | 2/2 | 1.30 | 2/2 |
| SWITCH | B | 0/2 | 2/2 | 1.30 | 2/2 |
| SWITCH | C | 0/2 | 2/2 | 1.30 | 2/2 |
| SWITCH | D | 0/2 | 2/2 | 1.30 | 2/2 |

Across all arms, the selected first action was identical within each task and environment:
- Query00188: `Transportation_Search_to_Final_4Steps`
- Query00347: `Search_Accommodation_Candidates`

Thus, in this small smoke cohort, removing the supplied plan and localizing the changed-tool information did not alter the first action. The model followed the incumbent first action in all 8 SWITCH observations, where that action had regret 1.30; it also followed it in all 8 RETAIN observations, where it was optimal.

There were no API errors, no missing or invalid tool calls, and no native tool-execution errors.

## Interpretation and limits

This is a successful pipeline smoke test and a descriptive signal consistent with persistent incumbent-action selection in these two tasks. It is not confirmatory evidence of a general plan-anchoring mechanism:
- only two preselected base tasks were used;
- there was one repetition per task/environment/arm;
- both tasks may share structural properties;
- first-action behavior alone does not establish full-trajectory outcomes;
- the result cannot identify whether the unchanged choice is caused by plan content, candidate generation, action priors, or another feature of the task/tool interface.

The result does show that the four prompt conditions did not rescue the SWITCH first action in this smoke cohort. It is therefore important not to interpret a successful RETAIN score as evidence that the prompt manipulation worked.

## Decision

The smoke test passed its engineering criteria. It does not justify changing prompts or introducing an intervention. The next planned step is a full audit of the frozen task definitions and scoring path, followed—only after a separate budget check/approval—by the 8-task, 128-request first-action screen. The two-task full-continuation check should remain a separately reported diagnostic and must not be selectively run only on favorable conditions.
