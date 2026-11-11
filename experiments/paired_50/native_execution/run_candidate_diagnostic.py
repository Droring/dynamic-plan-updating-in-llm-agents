#!/usr/bin/env python3
"""Execute frozen candidate-diagnostic requests through DeepSeek and native CostBench.

A paid run requires --live AND DEEPSEEK_API_KEY. Default is offline only.
All endpoints are independent requests. Never inserts oracle values in prompts.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import prepare_candidate_diagnostic as diagnostic
import run_four_arm_experiment as screen


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path, record):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def parse_json_object(value):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def score_text(endpoint, content, reference, available, feasible):
    obj = parse_json_object(content)
    oracle = set(reference["optimal_first_actions"])
    if endpoint == "consideration":
        names = obj.get("candidates")
        if not isinstance(names, list) or len(names) > 3 or not all(isinstance(x, str) for x in names):
            names = []
        return {
            "reported_candidates": names,
            "valid_candidates": bool(names) and len(set(names)) == len(names) and all(x in available and x in feasible for x in names),
            "reported_optimal_nonincumbent": any(x in oracle and x != reference["incumbent"] for x in names),
            "reported_incumbent": reference["incumbent"] in names,
        }
    name = obj.get("chosen_tool")
    return {
        "chosen_tool": name if isinstance(name, str) else None,
        "valid_choice": isinstance(name, str) and name in available and name in feasible,
        "optimal_choice": isinstance(name, str) and name in oracle,
    }


def summarize(records):
    by_cell = {}
    for endpoint in ("consideration", "comparison", "execution"):
        for env in ("RETAIN", "SWITCH"):
            rows = [x for x in records if x["endpoint"] == endpoint and x["environment"] == env]
            if not rows:
                continue
            by_cell[f"{env}/{endpoint}"] = {
                "attempted": len(rows),
                "successful_api": sum(x.get("provider_tokens", 0) > 0 for x in rows),
                "correct": sum(
                    bool(x.get("reported_optimal_nonincumbent")) if endpoint == "consideration"
                    else bool(x.get("optimal_choice")) if endpoint == "comparison"
                    else bool(x.get("optimal_executed"))
                    for x in rows
                ),
                "errors": sum(bool(x.get("error")) for x in rows),
            }
    paired = {}
    for r in records:
        if r["endpoint"] not in {"comparison", "execution"}:
            continue
        key = (r["query_id"], r["environment"], r["order"])
        paired.setdefault(key, {})[r["endpoint"]] = r
    consistency = []
    for (query, env, order), v in sorted(paired.items()):
        if "comparison" in v and "execution" in v:
            a, b = v["comparison"], v["execution"]
            consistency.append({
                "query_id": query, "environment": env, "order": order,
                "match": a.get("chosen_tool") is not None and a.get("chosen_tool") == b.get("executed_tool"),
                "comparison_optimal": a.get("optimal_choice"),
                "execution_optimal": b.get("optimal_executed"),
            })
    return {"cells": by_cell, "per_checkpoint_consistency": consistency,
            "consistency_matches": sum(x["match"] for x in consistency),
            "consistency_pairs": len(consistency)}


async def run_live(prep, costbench_root, out, cap, max_tokens, limit):
    from openai import AsyncOpenAI
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY missing; no requests sent")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Output directory not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    costbench = screen.native.load_costbench(costbench_root)
    selected, _, _ = screen.load_selected_trials(
        (Path(__file__).resolve().parent.parent / "generated"), costbench,
        json.loads((Path(__file__).resolve().parent / "FOUR_ARM_TASK_MANIFEST.json").read_text(encoding="utf-8")))
    prepared = {(t["query_id"], m["condition"]): p for t, _r, m, p in selected}
    refs = {(r["query_id"], r["environment"]): r for r in prep["reference"]}
    official_run = costbench["official_run"]
    rows = prep["prompts"][:limit]
    budget = screen.native.TokenBudget(cap)
    records = []
    request_path = out / "requests.jsonl"
    response_path = out / "responses.jsonl"
    async with AsyncOpenAI(base_url="https://api.deepseek.com", api_key=key, timeout=120) as client:
        for i, row in enumerate(rows, 1):
            id_key = (row["query_id"], row["environment"])
            p = prepared[id_key]
            ref = refs[id_key]
            endpoint = row["endpoint"]
            system = screen.native.make_official_system_prompt(official_run, p["task"])
            messages = [{"role": "system", "content": system}, {"role": "user", "content": row["user_message"]}]
            tools = row["tools"] if endpoint == "execution" else None
            reserve = screen.native.reservation_for_call(messages, row["tools"], max_tokens)
            if not budget.can_call(reserve):
                break
            record = {
                "query_id": row["query_id"], "environment": row["environment"],
                "endpoint": endpoint, "order": row["order"],
                "checkpoint_sha256": row["checkpoint_sha256"],
                "request_sha256": screen.native.canonical_sha({
                    "messages": messages, "tools": tools,
                    "max_tokens": max_tokens, "temperature": 0, "thinking": "disabled"}),
            }
            append_jsonl(request_path, {"metadata": record, "messages": messages, "tools": tools})
            budget.reserved += reserve
            started = time.monotonic()
            try:
                args = {
                    "model": screen.native.MODEL, "messages": messages,
                    "temperature": 0, "max_tokens": max_tokens,
                    "extra_body": {"thinking": {"type": "disabled"}},
                }
                if tools is not None:
                    args.update(tools=tools, tool_choice="required", parallel_tool_calls=False)
                response = await client.chat.completions.create(**args)
                budget.record_usage(response.usage)
                msg = response.choices[0].message
                record["provider_tokens"] = int(response.usage.total_tokens)
                record["model_reported"] = response.model
                record["assistant_content"] = msg.content
                interface_names = {x["function"]["name"] for x in p["tool_interfaces"]}
                feasible_names = {x for x, tool in p["tool_objects"].items()
                                  if set(tool.input_types).issubset(set(p["state"]))}
                if endpoint != "execution":
                    record.update(score_text(endpoint, msg.content, ref, interface_names, feasible_names))
                else:
                    calls = msg.tool_calls or []
                    record["tool_call_count"] = len(calls)
                    record["raw_tool_calls"] = [
                        {"name": x.function.name, "arguments": x.function.arguments} for x in calls]
                    record["executed_tool"] = calls[0].function.name if len(calls) == 1 else None
                    record["optimal_executed"] = False
                    if len(calls) != 1:
                        record["execution_status"] = "invalid_tool_call_count"
                    elif record["executed_tool"] not in (row["menu"] or []):
                        record["execution_status"] = "not_in_candidate_menu"
                    elif record["executed_tool"] not in feasible_names:
                        record["execution_status"] = "infeasible"
                    else:
                        tool = p["tool_objects"][record["executed_tool"]]
                        try:
                            output = official_run._execute_tool_simulation(
                                tool_obj=tool, arguments_str=calls[0].function.arguments,
                                refinement_level=screen.native.REFINEMENT_LEVEL,
                                available_tools=p["tool_objects"])
                            success = not (isinstance(output, str) and output.startswith(screen.native.ERROR_PREFIXES))
                            record["execution_status"] = "executed" if success else "tool_error"
                            record["tool_observation"] = str(output)
                            record["optimal_executed"] = bool(success and record["executed_tool"] in ref["optimal_first_actions"])
                        except Exception as exc:
                            record["execution_status"] = "execution_exception"
                            record["error"] = f"{type(exc).__name__}: {exc}"
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                record["provider_tokens"] = 0
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            record["accounted_tokens"] = budget.charged
            append_jsonl(response_path, record)
            records.append(record)
            save_json(out / "summary.json", {
                "status": "in_progress", "completed": len(records), "planned": len(rows),
                "accounted_tokens": budget.charged, **summarize(records)})
            print(json.dumps({"trial": i, "of": len(rows), "endpoint": endpoint,
                              "query_id": row["query_id"], "error": record.get("error"),
                              "tokens": budget.charged}), flush=True)
            if record.get("error") or budget.charged > cap:
                break
    summary = {
        "status": "complete" if len(records) == len(rows) and not any(r.get("error") for r in records) else "incomplete",
        "completed": len(records), "planned": len(rows),
        "accounted_tokens": budget.charged, "token_cap": cap,
        "base_tasks": 8, "eligible_checkpoints": 15,
        "reused_checkpoints": True, "independent_task_count": 8,
        **summarize(records)}
    save_json(out / "summary.json", summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--costbench-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("candidate_diagnostic_results"))
    ap.add_argument("--cap", type=int, default=600000)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--limit", type=int, default=75)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.limit <= 75 or args.max_tokens < 32 or args.cap < 1000:
        raise ValueError("Invalid request/budget limits")
    root = args.costbench_root.resolve()
    prep = diagnostic.prepare(root, (Path(__file__).resolve().parent.parent / "generated").resolve())
    print(json.dumps({"status": "prepared", "requests": args.limit,
                      "available_prompts": len(prep["prompts"]), "provider_calls": 0}))
    if not args.live:
        return
    result = asyncio.run(run_live(prep, root, args.out.resolve(), args.cap, args.max_tokens, args.limit))
    print(json.dumps(result, indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
