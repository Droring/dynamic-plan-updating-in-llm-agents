# Frozen full-continuation follow-up

## Goal
Check whether first-action differences in the four-arm mechanism screen survive native tool execution through goal completion.

## Pre-registered subset
- Base tasks: Query00188 (changed tool inside incumbent) and Query00347 (changed tool outside incumbent).
- RETAIN and SWITCH current environments, four prompt arms A/B/C/D.
- One continuation per cell: 2 x 2 x 4 = 16.
- Use repetition 1 from the completed 128-request formal run. No new first-action sampling.
- Formal source run: https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176
- Formal artifact: `four-arm-deepseek-formal`, ID 13697210404.
- Pinned upstream CostBench: `6424069f3f773ade076bcedbed302ed47cfb1837`.

## Protocol
The continuation runner rebuilds the exact checkpoint and verifies the archived prompt payload SHA-256 and checkpoint SHA-256. It injects the saved assistant first tool call and its saved native tool observation into the conversation, updates the typed state, then requests only subsequent actions from DeepSeek. The first tool call is **not resampled** and its original token usage is reported separately.

Use the same model `deepseek-flash`, thinking disabled, temperature 0, native tool registry and action execution helper. Maximum 12 tool steps including the archived first action. Hard cap 500,000 *additional* tokens. Stop on invalid tool, execution error, missing/multiple tool calls, API error, or step cap. All conditions are included in reporting, even when a trajectory fails.

Metrics: goal reached, full executed tool path, sum of native tool costs, full-path regret only if goal reached, preserved-incumbent suffix, additional model calls/tokens, failure reason. Report results by RETAIN/SWITCH and prompt arm, and at individual task level. First-action optimality is already known from the archived formal screen.

## Limitations
This is a two-task execution check, not a new independent test set. Query00188's original first tool may directly reach the goal; the experiment must report the resulting zero additional calls instead of forcing more calls. This sample cannot establish general full-trajectory improvement. Since the original provider response does not archive a native provider call ID, the continuation uses a deterministic synthetic tool-call ID only to preserve the message/tool-response protocol; the actual first tool name, arguments, result, and original prompt are retained.

## Authorization
Offline preflight is automatic and makes no provider calls. The billable continuation workflow is opt-in through the `run_paid_continuations` dispatch input, with `run_paid_formal` and `run_paid_smoke` disabled. Never select multiple paid inputs.
