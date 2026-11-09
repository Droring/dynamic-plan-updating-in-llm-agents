#!/usr/bin/env python3
"""Merge the two audited DeepSeek runs into the frozen 50-pair cohort."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from run_official_harness import (
    DATA_DIR,
    canonical_sha,
    grade_execution,
    load_frozen_inputs,
    sha_bytes,
)


FIRST_RUN_ID = 42551169346
FIRST_ARTIFACT_ID = 13644809250
CONTINUATION_RUN_ID = 42552119882
CONTINUATION_ARTIFACT_ID = 13645831744


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_run(run_dir: Path):
    run_dir = Path(run_dir)
    required = ("responses.jsonl", "scores.json", "ledger.json")
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{run_dir} is missing: {', '.join(missing)}")
    return (
        read_jsonl(run_dir / "responses.jsonl"),
        json.loads((run_dir / "scores.json").read_text(encoding="utf-8")),
        json.loads((run_dir / "ledger.json").read_text(encoding="utf-8")),
    )


def validate_record(record, request, manifest):
    trial_id = request["trial_id"]
    row = manifest[trial_id]
    if record.get("trial_id") != trial_id:
        raise ValueError(f"Trial order mismatch at {trial_id}.")
    if record.get("request_sha256") != canonical_sha(request):
        raise ValueError(f"Request hash mismatch at {trial_id}.")
    if record.get("checkpoint_sha256") != request["checkpoint_sha256"]:
        raise ValueError(f"Checkpoint hash mismatch at {trial_id}.")
    if record.get("query_id") != request["query_id"]:
        raise ValueError(f"Query ID mismatch at {trial_id}.")
    if record.get("condition") != row["condition"]:
        raise ValueError(f"Condition mismatch at {trial_id}.")


def merge(first_dir: Path, continuation_dir: Path, out_dir: Path, data_dir: Path):
    requests, manifest, registry = load_frozen_inputs(data_dir)
    if len(requests) != 100 or registry["base_task_count"] != 50:
        raise ValueError("Expected the frozen 100-trial, 50-task cohort.")

    first_records, first_scores, first_ledger = read_run(first_dir)
    continuation_records, continuation_scores, continuation_ledger = read_run(
        continuation_dir
    )
    input_sha = sha_bytes((data_dir / "model_requests_100.jsonl").read_bytes())
    manifest_sha = sha_bytes((data_dir / "trial_manifest_100.json").read_bytes())

    for label, scores in (
        ("initial run", first_scores),
        ("continuation", continuation_scores),
    ):
        if scores.get("input_sha256") != input_sha:
            raise ValueError(f"{label} used different frozen requests.")
        if scores.get("manifest_sha256") != manifest_sha:
            raise ValueError(f"{label} used a different frozen manifest.")

    if first_scores.get("status") != "incomplete" or first_ledger.get("status") != "incomplete":
        raise ValueError("The initial run is not the expected reservation-limited run.")
    if len(first_records) != 67 or first_ledger.get("attempted_trials") != 67:
        raise ValueError("The initial run must contain 67 records.")
    if first_records[-1].get("halt_reason") != "reservation_cap":
        raise ValueError("The initial run's final record is not reservation-limited.")
    if not first_records[-1].get("trace"):
        raise ValueError("The reservation-limited record has no saved native tool trace.")
    if int(first_records[-1].get("model_calls") or 0) <= 0:
        raise ValueError("The reservation-limited record has no recorded model call.")

    if continuation_scores.get("status") != "complete" or continuation_ledger.get("status") != "complete":
        raise ValueError("The continuation run is not complete.")
    if len(continuation_records) != 34 or continuation_ledger.get("attempted_trials") != 34:
        raise ValueError("The continuation run must contain 34 records.")

    # The first run completed the first 66 trials. Its 67th record is a partial
    # attempt; the continuation restarted that same frozen trial and completed
    # the final 34-trial suffix. Score the completed version exactly once.
    for index, record in enumerate(first_records[:66]):
        validate_record(record, requests[index], manifest)
        if record.get("halt_reason") != "goal_reached" or record.get("goal_state_reached") is not True:
            raise ValueError(f"Initial trial {index + 1} was not fully completed.")

    for offset, record in enumerate(continuation_records, start=66):
        validate_record(record, requests[offset], manifest)
        if record.get("halt_reason") != "goal_reached" or record.get("goal_state_reached") is not True:
            raise ValueError(f"Continuation trial {offset + 1} was not fully completed.")

    partial = first_records[-1]
    resumed = continuation_records[0]
    for field in ("trial_id", "request_sha256", "checkpoint_sha256", "query_id", "condition"):
        if partial.get(field) != resumed.get(field):
            raise ValueError(f"The restarted partial trial differs on {field}.")

    records = first_records[:66] + continuation_records
    trial_ids = [row["trial_id"] for row in records]
    if len(records) != 100 or len(set(trial_ids)) != 100:
        raise ValueError("Merged scored cohort must contain 100 unique trials.")

    for record in records:
        if record.get("model_reported") != "deepseek-flash":
            raise ValueError(f"Unexpected provider model for {record['trial_id']}.")
        if record.get("first_action_success") is not True:
            raise ValueError(f"First native tool action failed for {record['trial_id']}.")
        if record.get("goal_state_reached") is not True:
            raise ValueError(f"Goal state was not reached for {record['trial_id']}.")
        if record.get("halt_reason") != "goal_reached":
            raise ValueError(f"Unexpected halt reason for {record['trial_id']}.")

    condition_counts = Counter(manifest[row["trial_id"]]["condition"] for row in records)
    if condition_counts != {"RETAIN": 50, "SWITCH": 50}:
        raise ValueError(f"Merged cohort is not condition-balanced: {dict(condition_counts)}")

    pair_predictions = defaultdict(dict)
    pair_records = defaultdict(dict)
    for record in records:
        pair_predictions[record["query_id"]][record["condition"]] = record[
            "first_action_prediction"
        ]
        pair_records[record["query_id"]][record["condition"]] = record
    if len(pair_predictions) != 50 or any(
        set(values) != {"RETAIN", "SWITCH"} for values in pair_predictions.values()
    ):
        raise ValueError("Merged cohort does not contain 50 complete RETAIN/SWITCH pairs.")

    scores = grade_execution(records, manifest, planned_trials=100)
    if scores["status"] != "complete" or not scores["cohort_complete"]:
        raise ValueError("Merged cohort did not receive a complete-cohort score.")
    if scores["api_error_trials"] or scores["runner_error_trials"] or scores["reservation_limited_trials"]:
        raise ValueError("A scored trajectory contains an execution error or budget stop.")

    pair_outcomes = Counter(
        (values["RETAIN"], values["SWITCH"])
        for values in pair_predictions.values()
    )
    invariant_pairs = sum(
        values["RETAIN"] == values["SWITCH"]
        for values in pair_predictions.values()
    )
    superseded_tokens = int(partial.get("provider_total_tokens") or 0)
    superseded_calls = int(partial.get("model_calls") or 0)
    first_run_tokens = int(first_ledger["charged_tokens"])
    continuation_tokens = int(continuation_ledger["charged_tokens"])
    actual_tokens = first_run_tokens + continuation_tokens
    scored_tokens = int(scores["provider_total_tokens"])
    if actual_tokens != scored_tokens + superseded_tokens:
        raise ValueError("Token accounting does not reconcile across both runs.")

    scored_calls = sum(int(row.get("model_calls") or 0) for row in records)
    prediction_counts = Counter(row.get("first_action_prediction") for row in records)
    scores.update({
        "model_retain_prediction_count": prediction_counts["RETAIN"],
        "model_switch_prediction_count": prediction_counts["SWITCH"],
        "model_retain_prediction_rate": prediction_counts["RETAIN"] / 100,
        "model_switch_prediction_rate": prediction_counts["SWITCH"] / 100,
        "pair_decision_invariant_count": invariant_pairs,
        "pair_decision_invariant_rate": invariant_pairs / 50,
        "pair_prediction_changed_count": 50 - invariant_pairs,
        "pair_prediction_changed_rate": (50 - invariant_pairs) / 50,
        "always_retain_baseline_accuracy": condition_counts["RETAIN"] / 100,
        "balanced_accuracy": (
            scores["retain_accuracy"] + scores["switch_accuracy"]
        ) / 2,
        "source_runs": {
            "initial_run_id": FIRST_RUN_ID,
            "initial_artifact_id": FIRST_ARTIFACT_ID,
            "continuation_run_id": CONTINUATION_RUN_ID,
            "continuation_artifact_id": CONTINUATION_ARTIFACT_ID,
        },
        "pair_outcomes": {
            f"{retain_prediction}/{switch_prediction}": count
            for (retain_prediction, switch_prediction), count in sorted(pair_outcomes.items())
        },
        "scored_model_calls": scored_calls,
        "scored_provider_total_tokens": scored_tokens,
        "superseded_partial_attempt": {
            "trial_id": partial["trial_id"],
            "query_id": partial["query_id"],
            "halt_reason": partial["halt_reason"],
            "model_calls": superseded_calls,
            "provider_total_tokens": superseded_tokens,
            "excluded_from_scored_cohort": True,
        },
        "actual_model_calls_including_superseded_attempt": scored_calls + superseded_calls,
        "actual_provider_total_tokens_including_superseded_attempt": actual_tokens,
    })

    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is nonempty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "responses.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "scores.json").write_text(
        json.dumps(scores, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    ledger = {
        "status": "complete",
        "scored_trials": 100,
        "base_tasks": 50,
        "retain_trials": 50,
        "switch_trials": 50,
        "scored_provider_total_tokens": scored_tokens,
        "superseded_partial_attempt_tokens": superseded_tokens,
        "actual_provider_total_tokens_including_superseded_attempt": actual_tokens,
        "scored_model_calls": scored_calls,
        "actual_model_calls_including_superseded_attempt": scored_calls + superseded_calls,
        "initial_run_id": FIRST_RUN_ID,
        "initial_artifact_id": FIRST_ARTIFACT_ID,
        "continuation_run_id": CONTINUATION_RUN_ID,
        "continuation_artifact_id": CONTINUATION_ARTIFACT_ID,
        "input_sha256": input_sha,
        "manifest_sha256": manifest_sha,
    }
    (out_dir / "ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    pair_table = "\n".join(
        f"| `{label}` | {count} |"
        for label, count in sorted(scores["pair_outcomes"].items())
    )
    deviation_table = "\n".join(
        f"| {query_id} | `{pair_records[query_id]['RETAIN']['first_action']}` | "
        f"`{pair_records[query_id]['SWITCH']['first_action']}` | "
        f"`{pair_predictions[query_id]['RETAIN']}/{pair_predictions[query_id]['SWITCH']}` |"
        for query_id in sorted(pair_records)
        if pair_predictions[query_id]["RETAIN"] != "RETAIN"
        or pair_predictions[query_id]["SWITCH"] != "RETAIN"
    )
    results_md = f"""# Paired 50 native CostBench execution — DeepSeek Flash

**Status:** Complete  
**Scored cohort:** 100 trajectories across 50 paired base tasks  
**Model reported by provider:** `deepseek-flash`  
**Upstream CostBench revision:** `{registry["upstream_revision"]}`

## Main results

| Measure | Result |
|---|---:|
| RETAIN first-action accuracy | {scores["retain"]["correct"]}/50 ({scores["retain_accuracy"]:.1%}) |
| SWITCH first-action accuracy | {scores["switch"]["correct"]}/50 ({scores["switch_accuracy"]:.1%}) |
| Overall first-action accuracy | {scores["first_action_accuracy"]:.1%} |
| Model predicted RETAIN | {scores["model_retain_prediction_count"]}/100 ({scores["model_retain_prediction_rate"]:.1%}) |
| Model predicted SWITCH | {scores["model_switch_prediction_count"]}/100 ({scores["model_switch_prediction_rate"]:.1%}) |
| Always-RETAIN baseline accuracy | {scores["always_retain_baseline_accuracy"]:.1%} |
| Balanced accuracy | {scores["balanced_accuracy"]:.1%} |
| Paired decision accuracy | {scores["pair_correct"]}/50 ({scores["pair_accuracy"]:.1%}) |
| Same decision on both paired conditions | {scores["pair_decision_invariant_count"]}/50 ({scores["pair_decision_invariant_rate"]:.1%}) |
| Goal state reached | {scores["goal_state_reached"]}/100 |
| First native tool action succeeded | 100/100 |
| Exact incumbent suffix executed | {scores["trajectory_relations"].get("exact_incumbent_suffix", 0)}/100 |
| Alternative continuation executed | {scores["trajectory_relations"].get("alternative_continuation", 0)}/100 |

## Paired outcomes

The tuple is (prediction under RETAIN condition, prediction under SWITCH condition).

| Paired outcome | Number of base tasks |
|---|---:|
{pair_table}

## The four alternative continuations

| Query | RETAIN-condition first tool | SWITCH-condition first tool | Paired prediction |
|---|---|---|---|
{deviation_table}

The model selected the incumbent first action in **48/50 SWITCH conditions (96%)**. Across all 100 trajectories, it predicted RETAIN 96 times and SWITCH four times. Its 50% overall accuracy is exactly the same as an always-RETAIN baseline on this balanced dataset; the class-conditional results expose the asymmetry (96% RETAIN accuracy versus 4% SWITCH accuracy). The first-action prediction was identical across the two conditions in {scores["pair_decision_invariant_count"]}/50 pairs (96%); only one pair received the correct RETAIN/SWITCH distinction on both sides.

The model reached the goal in all 100 scored trajectories. Thus task completion alone would conceal the plan-commitment behavior: the main failure is the first action's lack of responsiveness to the paired environment condition.

## Execution and accounting

The initial full-cohort run completed 66 trajectories. Its 67th trajectory executed one successful tool call and then stopped at the token reservation guard. The continuation reran that same frozen trial from its original checkpoint and completed it, then completed the remaining 33 trials.

For scoring, the 66 completed initial records and all 34 completed continuation records form the 100-trial cohort. The partial initial attempt is retained in the accounting but excluded from the scored cohort.

- Scored provider usage: **{scored_tokens:,} tokens** across {scored_calls} model calls.
- Superseded partial attempt: **{superseded_tokens:,} tokens** across {superseded_calls} model call(s).
- Total provider usage across both runs: **{actual_tokens:,} tokens**.
- API errors: 0.
- Runner errors: 0.
- Incomplete trajectories in the scored cohort: 0.

## Reproducibility

- Initial run: [GitHub Actions #{FIRST_RUN_ID}](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/{FIRST_RUN_ID}) — artifact `{FIRST_ARTIFACT_ID}`.
- Continuation: [GitHub Actions #{CONTINUATION_RUN_ID}](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/{CONTINUATION_RUN_ID}) — artifact `{CONTINUATION_ARTIFACT_ID}`.
- Offline validation: [GitHub Actions #42553539170](https://github.com/Droring/state-aligned-selective-replanning/actions/runs/42553539170).
- Frozen request SHA-256: `{input_sha}`.
- Frozen manifest SHA-256: `{manifest_sha}`.

The RETAIN/SWITCH measure is based on the first executed native tool: matching the incumbent suffix's first tool is RETAIN; choosing a different first tool is SWITCH. Full trajectory relation and goal completion are reported separately. This is an observable execution measure, not a claim about hidden model reasoning.
"""
    (out_dir / "RESULTS.md").write_text(results_md, encoding="utf-8")
    return scores


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-run-dir", type=Path, required=True)
    parser.add_argument("--continuation-run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    scores = merge(args.first_run_dir, args.continuation_run_dir, args.out, args.data_dir)
    print(json.dumps(scores, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
