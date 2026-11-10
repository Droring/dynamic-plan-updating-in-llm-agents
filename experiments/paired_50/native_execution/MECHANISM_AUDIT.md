# Four-Arm Smoke-Test Mechanism Audit

## Scope and provenance

This audit follows the 16-request DeepSeek smoke test and uses only archived request payloads, model responses, the frozen eight-task manifest, the pinned CostBench solver, and offline GitHub Actions validation. No additional model/API calls were made.

- Smoke run: [GitHub Actions #42658715641](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42658715641)
- Offline candidate audit: [GitHub Actions #42663231253](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42663231253)
- Branch: `research/four-arm-mechanism-screen`
- Audited commit: `ef5f0eed4ee7449b911e333f2d74c949b7318733`

## 1. Smoke result replication

All 16 requests completed, all first tool calls were natively executed, and all were scored. There were no API errors, invalid tools, missing inputs, or tool execution errors. The accounted usage was 88,968 tokens under the 500,000-token hard cap.

For each of the two base tasks, the first action was identical across A/B/C/D within each environment:
- Query00188 SWITCH: all four arms selected `Transportation_Search_to_Final_4Steps`; the native-optimal first action was `Transportation_Search_Planning_to_Step2`; regret = 1.30.
- Query00347 SWITCH: all four arms selected `Search_Accommodation_Candidates`; the native-optimal first action was `Accommodation_Search_Planning_to_Step2`; regret = 1.30.
- Both RETAIN checkpoints selected an optimal first action in all four arms.

## 2. Candidate availability audit across all eight frozen tasks

The offline runner independently computed native-optimal first actions for all 16 task/environment checkpoints. For every checkpoint, each oracle-optimal first-action tool:
1. existed in the exact tool interface sent to the model;
2. existed in the reconstructed native tool registry; and
3. had all required input types present in the checkpoint state.

Result: **16/16 checkpoint candidates were available and type-feasible.** No oracle-optimal first action was blocked by a missing input or absent tool definition.

| Task | Category | Changed tool in incumbent suffix? | SWITCH incumbent first action optimal? | SWITCH oracle-optimal first action | Candidate available and feasible? |
|---|---|---:|---:|---|---:|
| Query00188 | Transportation | Yes | No | `Transportation_Search_Planning_to_Step2` | Yes |
| Query00403 | Accommodation | Yes | Yes | `Search_Accommodation_Candidates` | Yes |
| Query00550 | Attraction | Yes | No | `Search_Attraction_Candidates` | Yes |
| Query00706 | Dining | Yes | No | `Dining_Refine_to_Step2` | Yes |
| Query00347 | Accommodation | No | No | `Accommodation_Search_Planning_to_Step2` | Yes |
| Query00518 | Attraction | No | No | `Attraction_Refine_to_Step2` | Yes |
| Query00685 | Dining | No | No | `Dining_Refinement_Step1` | Yes |
| Query00858 | Shopping | No | No | `Shopping_Search_to_Final_4Steps` | Yes |

Seven of the eight SWITCH checkpoints make the incumbent first action suboptimal. Query00403 is an important exception: the changed tool is later in the incumbent suffix, while the incumbent first action remains oracle-optimal. Therefore a first-action metric alone cannot detect every downstream replanning failure. Query00403 must remain visible in reporting and must not be counted as a first-action SWITCH error.

## 3. Independent optimality cross-check on the two live smoke tasks

A second shortest-path calculation was reconstructed from the serialized tool interfaces (tool costs, required inputs, output types) and agrees with the native solver values:

| Task / condition | Native and independent optimal value | Incumbent first-action value | Difference |
|---|---:|---:|---:|
| Query00188 RETAIN | 79.03 | 79.03 | 0.00 |
| Query00188 SWITCH | 79.15 | 80.45 | 1.30 |
| Query00347 RETAIN | 77.68 | 77.68 | 0.00 |
| Query00347 SWITCH | 76.38 | 77.68 | 1.30 |

For the two SWITCH cases, the optimal first-action tools have the same three required input types as the available checkpoint data. The model-selected incumbent actions are also executable, so this is not a tool-call validity failure.

## 4. Prompt and information audit

The exact archived payloads were compared:
- System messages and tool interfaces are identical across A/B/C/D within each task/environment checkpoint.
- A to B adds only a neutral sentence stating the changed tool's current cost.
- A to C removes only the incumbent-plan sentence.
- B to D removes only the incumbent-plan sentence.

Crucial qualification: all four arms already receive complete tool descriptions containing **current costs for every available tool**. Thus B/D do not reveal otherwise unavailable cost information. They add a localized repetition/salience cue for the changed tool's current cost. The experiment therefore tests a current-cost reminder, not whether the model can access the current price at all.

## 5. Mechanism interpretation

What the evidence rules out:
- The optimal alternative was not omitted from the tool interface.
- The optimal alternative was not blocked by missing typed inputs.
- The smoke-test score was not caused by invalid tool calls or native execution errors.
- The unchanged first action was not caused by the plan sentence alone: it persisted in the plan-omitted C/D arms.

What the evidence does not identify:
- Whether the model generated the alternative internally and rejected it;
- whether it failed to generate or retrieve the alternative;
- whether tool-name semantics, composite-tool familiarity, or another action prior dominated;
- whether a later action would have been corrected after the first action.

A selected tool call is an observable choice, not a trace of the model's complete candidate search or private comparison process. The correct conclusion is that **available, feasible, oracle-better alternatives were not selected at the first decision point in the observed SWITCH smoke cases**, even after plan removal and a current-cost reminder. This is evidence of an action-selection failure under the tested interface, not yet a unique mechanism explanation.

## 6. Next experimental decision

The engineering and scoring audits pass. The eight-task offline design prepares 128 requests (16 per environment-by-prompt cell), with a conservative reservation ceiling of 3,443,584 tokens and zero provider calls.

The 16-request smoke test used 88,968 tokens (5,560.5 mean per request). A simple usage-based projection for 128 requests is approximately 711,744 tokens, but this is only a planning estimate: task prompts differ in tool count/description length and the archived response records do not provide an input/output token split for a precise currency estimate. The hard reservation ceiling remains 3,443,584 tokens.

The formal 128-request run has **not** been launched and requires separate user approval. Before that run, the study should explicitly label B/D as current-cost reminder conditions and retain Query00403 as a first-action-optimal SWITCH checkpoint, rather than misclassifying it as a first-action error.
