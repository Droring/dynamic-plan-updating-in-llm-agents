# Plan-handoff run recovery record

## Failed attempt

- Workflow run: [42984367048](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42984367048)
- The offline-validation job succeeded. The paid `paid-plan-handoff` job failed in `run_plan_handoff_experiment.py` after the first trial returned from `run_one`.
- Failure: `AttributeError: module 'run_official_harness' has no attribute 'append_jsonl'`.
- The failure occurred while appending the first trajectory result. The artifact [13838443689](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42984367048/artifacts/13838443689) contains the restoration and prompt-preflight files, but no live response file, call journal, or token ledger.
- Consequently, the first trial's model/provider outcome and token usage cannot be reconstructed from the archived run. Do not treat this run as an experimental result, and do not claim that the first trial definitely received a successful model response.

## Repair

The live runner now:

1. Implements its own JSONL append routine and flushes each record with `fsync`; it no longer calls a helper absent from the native harness.
2. Writes a per-call journal containing call starts, returned assistant tool calls, provider token usage, tool results, and API errors.
3. Atomically writes a progress ledger after each journal event and each completed trajectory.
4. Stops after an API or internal execution error instead of silently continuing.
5. Supports resume from a durable completed-trial prefix. It verifies trial order, frozen payload hashes, token-cap settings, and ledger consistency.
6. Refuses to resume when the previous run stopped inside a trial, because replaying that trial could duplicate an unrecorded provider charge.
7. Uploads the response records, event journal, ledger, and summary together.

## Successful retry

- Workflow run: [42997923650](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42997923650)
- The repaired `paid-plan-handoff` job completed successfully.
- All **80/80** frozen trajectories reached the goal; there were zero unknown provider outcomes.
- The run used 120 model calls and recorded 725,465 provider tokens.
- The [artifact](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42997923650/artifacts/13844657416) contains requests, restoration and prompt preflights, responses, call journal, ledger and summary.
- The retry used a fresh frozen request set and did not replay the uncertain trial from the failed attempt. The failed attempt remains excluded from analysis.

## Budget treatment for the retry

The originally approved total cap was 3,443,584 tokens. Since the failed run's provider usage was not persisted, the retry reserves 1,000,000 tokens as an operational allowance for that orphaned attempt. The retry's effective cap is therefore 2,443,584 tokens.

This 1,000,000-token allowance is **not a measured usage figure**. The cumulative usage across the failed attempt and retry cannot be certified exactly from GitHub artifacts alone. If exact billing reconciliation is required, check the DeepSeek account usage page for the failed run's time window.

The successful retry used an empty `resume_plan_handoff_run_id`; the uncertain trial from run 42984367048 was not replayed. Run 42997923650 is complete and is not a pending continuation.

## Validation status

The repaired runner and its resume tests passed the full offline validation in [run 42987006523](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42987006523). This validation made zero provider calls. A paid retry has not yet been started.


## Current status

The five-task plan-handoff development screen is complete; see [PLAN_HANDOFF_STATE_TRACKING_RESULTS.md](PLAN_HANDOFF_STATE_TRACKING_RESULTS.md). The later plan-status annotation follow-up has passed offline preflight, but its paid job has not been launched.
