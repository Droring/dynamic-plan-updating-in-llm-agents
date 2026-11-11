"""Post-hoc scoring and durable logging; never imported by policy modules."""
from __future__ import annotations
from collections import defaultdict
import json, math, os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EPSILON = 1e-6

def path_value(path: Sequence[str], current_tool_costs: Mapping[str, float]) -> float:
    total = 0.0
    for name in path:
        if name not in current_tool_costs:
            raise ValueError(f"scoring path contains unknown tool: {name}")
        total += float(current_tool_costs[name])
    if not math.isfinite(total):
        raise ValueError("path value is not finite")
    return round(total, 9)

def score_trajectory(*, task_id: str, condition: str, decision: str,
                     goal_reached: bool, executed_path: Sequence[str],
                     committed_path: Sequence[str], incumbent_path: Sequence[str],
                     current_tool_costs: Mapping[str, float],
                     oracle_optimal_value: float,
                     usage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Score after execution; labels and oracle values stay in the evaluator."""
    if condition not in {"RETAIN", "SWITCH"}:
        raise ValueError("unknown evaluation condition")
    if decision not in {"RETAIN", "SWITCH", "STOP"}:
        raise ValueError("unknown policy decision")
    actual = path_value(executed_path, current_tool_costs) if executed_path else None
    incumbent = path_value(incumbent_path, current_tool_costs)
    committed_match = list(executed_path) == list(committed_path)
    if condition == "RETAIN":
        execution_correct = bool(goal_reached and committed_match and actual is not None
                                 and abs(actual-incumbent) <= EPSILON)
    else:
        execution_correct = bool(goal_reached and committed_match and actual is not None
                                 and actual < incumbent-EPSILON)
    use = dict(usage or {})
    usage_fields = {
        "planning_calls": int(use.get("planning_calls", 0)),
        "parameter_calls": int(use.get("parameter_calls", 0)),
        "planning_tokens": int(use.get("planning_tokens", 0)),
        "parameter_tokens": int(use.get("parameter_tokens", 0)),
        "total_model_calls": int(use.get("total_model_calls", 0)),
        "total_tokens": int(use.get("total_tokens", 0)),
        "decision_latency_seconds": float(use.get("decision_latency_seconds", 0.0)),
    }
    if any(v < 0 for k, v in usage_fields.items() if k != "decision_latency_seconds"):
        raise ValueError("usage counters cannot be negative")
    if not math.isfinite(usage_fields["decision_latency_seconds"]) or usage_fields["decision_latency_seconds"] < 0:
        raise ValueError("decision latency must be finite and non-negative")
    return {
        "task_id": task_id, "condition": condition, "decision": decision,
        "decision_correct": decision == condition, "goal_reached": bool(goal_reached),
        "executed_path": list(executed_path), "committed_path": list(committed_path),
        "committed_path_match": committed_match,
        "incumbent_path": list(incumbent_path),
        "executed_path_value": actual, "incumbent_path_value": incumbent,
        "oracle_optimal_value": float(oracle_optimal_value),
        "execution_correct": execution_correct,
        "exact_optimal_trajectory": bool(goal_reached and actual is not None
                                         and abs(actual-float(oracle_optimal_value)) <= EPSILON),
        **usage_fields,
    }

def summarize_records(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    if not rows:
        raise ValueError("cannot summarize an empty evaluation")
    def average(key: str) -> float:
        return sum(float(row.get(key, 0)) for row in rows) / len(rows)
    return {
        "trajectory_count": len(rows),
        "decision_balanced_accuracy": balanced_accuracy(rows, "decision_correct"),
        "execution_grounded_balanced_accuracy": balanced_accuracy(rows, "execution_correct"),
        "pair_accuracy": pair_accuracy(rows, "execution_correct"),
        "goal_success_rate": average("goal_reached"),
        "exact_optimal_trajectory_rate": average("exact_optimal_trajectory"),
        "mean_planning_calls": average("planning_calls"),
        "mean_parameter_calls": average("parameter_calls"),
        "mean_total_model_calls": average("total_model_calls"),
        "mean_planning_tokens": average("planning_tokens"),
        "mean_parameter_tokens": average("parameter_tokens"),
        "mean_total_tokens": average("total_tokens"),
        "mean_decision_latency_seconds": average("decision_latency_seconds"),
    }

def balanced_accuracy(records: Iterable[Mapping[str, Any]],
                      key: str = "execution_correct") -> float:
    rows = list(records)
    rates = {}
    for condition in ("RETAIN", "SWITCH"):
        subset = [x for x in rows if x.get("condition") == condition]
        if not subset:
            raise ValueError(f"missing {condition} evaluation records")
        rates[condition] = sum(bool(x.get(key)) for x in subset)/len(subset)
    return (rates["RETAIN"]+rates["SWITCH"])/2.0

def pair_accuracy(records: Iterable[Mapping[str, Any]],
                   key: str = "execution_correct") -> float:
    pairs: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in records:
        task, condition = str(row["task_id"]), str(row["condition"])
        if condition in pairs[task]:
            raise ValueError(f"duplicate paired condition for {task}")
        pairs[task][condition] = bool(row.get(key))
    complete = [x for x in pairs.values() if set(x) == {"RETAIN", "SWITCH"}]
    if not complete:
        raise ValueError("no complete RETAIN/SWITCH task pairs")
    return sum(x["RETAIN"] and x["SWITCH"] for x in complete)/len(complete)

def append_jsonl_durable(path: str | Path, record: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)+"\n"
    with target.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())

def write_json_atomic(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name+".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True,
                  indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
