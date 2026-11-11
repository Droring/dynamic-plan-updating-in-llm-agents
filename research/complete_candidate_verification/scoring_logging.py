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
                     incumbent_path: Sequence[str],
                     current_tool_costs: Mapping[str, float],
                     oracle_optimal_value: float) -> dict[str, Any]:
    """Score after execution; condition and oracle value are evaluator-only."""
    if condition not in {"RETAIN", "SWITCH"}:
        raise ValueError("unknown evaluation condition")
    if decision not in {"RETAIN", "SWITCH", "STOP"}:
        raise ValueError("unknown policy decision")
    actual = path_value(executed_path, current_tool_costs) if executed_path else None
    incumbent = path_value(incumbent_path, current_tool_costs)
    if condition == "RETAIN":
        execution_correct = bool(goal_reached and actual is not None
                                 and abs(actual-incumbent) <= EPSILON)
    else:
        execution_correct = bool(goal_reached and actual is not None
                                 and actual < incumbent-EPSILON)
    return {
        "task_id": task_id, "condition": condition, "decision": decision,
        "decision_correct": decision == condition, "goal_reached": bool(goal_reached),
        "executed_path": list(executed_path), "incumbent_path": list(incumbent_path),
        "executed_path_value": actual, "incumbent_path_value": incumbent,
        "oracle_optimal_value": float(oracle_optimal_value),
        "execution_correct": execution_correct,
        "exact_optimal_trajectory": bool(goal_reached and actual is not None
                                         and abs(actual-float(oracle_optimal_value)) <= EPSILON),
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
