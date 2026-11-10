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

## Post-run mechanism audit: candidate availability and prompt integrity

A separate audit of the archived request payloads and tool schemas was completed after the smoke run.

### 1. The optimal alternatives were available and feasible

The optimal first-action alternatives were present in the exact native tool interface sent to DeepSeek. Their required input types were all present in the checkpoint state.

| Task / condition | Model first action | Independently reconstructed optimal first action | Feasibility |
|---|---|---|---|
| Query00188 / SWITCH | `Transportation_Search_to_Final_4Steps` | `Transportation_Search_Planning_to_Step2` | All required inputs present |
| Query00347 / SWITCH | `Search_Accommodation_Candidates` | `Accommodation_Search_Planning_to_Step2` | All required inputs present |

An independent shortest-path reconstruction from the serialized tool schemas (required inputs, output types, and costs) agrees with the native CostBench solver:
- Query00188 / SWITCH: optimal continuation value 79.15; the selected incumbent composite action costs 80.45; first-action regret is 1.30. The optimal alternative is `Transportation_Search_Planning_to_Step2` followed by `Select_Final_Transportation`.
- Query00347 / SWITCH: optimal continuation value 76.38; the selected incumbent first action leads to a continuation value of 77.68; first-action regret is 1.30. The optimal alternative is `Accommodation_Search_Planning_to_Step2` followed by `Select_Final_Accommodation`.

The same reconstruction matches the RETAIN oracle values (79.03 for Query00188 and 77.68 for Query00347). This independently supports the action-regret calculations for these two tasks.

### 2. What the model actually saw

The complete current tool schemas—including each tool's current cost, input requirements, output type, and description—were supplied in all four arms. The B/D localized-fact sentence therefore repeated a current cost already visible in the tool interface; it did not provide previously unavailable cost information. In A/C, the same current costs were still present in the tool definitions.

Exact prompt-diff checks confirm:
- A to B: only the neutral sentence naming the changed tool's current cost was added.
- A to C: only the incumbent-plan sentence was removed.
- B to D: only the incumbent-plan sentence was removed.
- System prompts and tool interfaces were byte-identical across A/B/C/D within each task and environment checkpoint.

This makes the manipulation more precisely an **attention/localization reminder plus plan-content ablation**, not a contrast between hidden and newly revealed cost information.

### 3. What the result supports—and what it does not

The two SWITCH alternatives were not absent from the interface and were not blocked by missing input types. The model nevertheless selected the same incumbent first action in A/B/C/D.

This rules out a simple explanation that the cheaper first-action alternative was unavailable in the tool list or infeasible from the current typed state. It does **not** establish whether the model internally failed to generate the alternative, generated it but miscompared its value, or applied a strong prior for the familiar action. A single selected tool call does not expose the model's unchosen candidate set or internal comparison.

The unchanged behavior after plan removal also means the smoke result cannot be attributed specifically to the displayed incumbent-plan sentence. The result is consistent with a broader action-selection preference or task/tool-description effect. Distinguishing these explanations requires a controlled candidate-set diagnostic, not a post-hoc interpretation of the model's rationale.

### 4. Revised next-step recommendation

Before spending the 128-request budget, the next diagnostic should be narrowly targeted:
1. Preserve the same checkpoint and native tool schemas.
2. Branch an independent diagnostic request from the checkpoint; do not feed its answer back into the original first-action trajectory.
3. Provide a balanced, randomized list of feasible candidate continuations—including the oracle-best path, the incumbent path, and a feasible but worse alternative—without costs, rankings, or a recommended choice.
4. Ask for one executable first action, then score it with the same native solver.
5. Compare this with the original free tool-choice condition on a small, predeclared subset.

This tests whether making alternatives explicit changes action selection. It still does not directly reveal private internal search, and oracle-supplied candidates must be reported as a diagnostic assistance condition rather than a deployable method.

No additional model calls were made during this audit.

