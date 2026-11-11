#!/usr/bin/env python3
"""Gate plan-omitted candidate actions against the retained plan.

Uses archived *real* C-arm candidates from the formal four-arm study.
Only the separate text-only evidence-review gate may call DeepSeek.
No solver output is included in prompts; scoring occurs after selection.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import run_four_arm_experiment as screen

HERE = Path(__file__).resolve().parent
ARCHIVE_RUN = 42665117176


def stable_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_candidates(archive: Path):
    path = archive / "responses.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Missing formal archived DeepSeek record: {path}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 128:
        raise ValueError(f"Expected 128 archived four-arm responses, got {len(records)}")
    candidates = {}
    for row in records:
        key = (row["query_id"], row["environment_condition"], row["repetition"], row["prompt_condition"])
        if key in candidates:
            raise ValueError(f"Duplicate archived trial: {key}")
        candidates[key] = row
    return candidates


def prepare(archive, costbench_root, data_dir):
    os.chdir(costbench_root)
    manifest = json.loads((HERE / "FOUR_ARM_TASK_MANIFEST.json").read_text(encoding="utf-8"))
    cb = screen.native.load_costbench(costbench_root)
    if cb["revision"] != manifest["source"]["upstream_costbench_revision"]:
        raise ValueError("Pinned upstream mismatch")
    selected, _, _ = screen.load_selected_trials(data_dir, cb, manifest)
    indexed = {(t["query_id"], m["condition"]): (t, p) for t, _r, m, p in selected}
    archived = load_candidates(archive)
    rows = []
    for task in manifest["tasks"]:
        for environment in ("RETAIN", "SWITCH"):
            _, p = indexed[(task["query_id"], environment)]
            incumbent = p["incumbent_suffix"][0]
            current_interface = {x["function"]["name"] for x in p["tool_interfaces"]}
            for rep in (1, 2):
                old = archived[(task["query_id"], environment, rep, "A")]
                candidate = archived[(task["query_id"], environment, rep, "C")]
                if old.get("first_action") != incumbent:
                    raise ValueError("Original A-arm action not incumbent")
                if candidate.get("first_action_status") != "executed":
                    raise ValueError("Plan-omitted C candidate was not natively executed")
                if candidate["checkpoint_sha256"] != p["checkpoint_sha256"]:
                    raise ValueError("Checkpoint mismatch in archived C candidate")
                name = candidate["first_action"]
                if name not in current_interface:
                    raise ValueError("Unknown candidate tool")
                tool = p["tool_objects"][name]
                if not set(tool.input_types).issubset(set(p["state"])):
                    raise ValueError("Candidate tool infeasible")
                row = {
                    "query_id": task["query_id"],
                    "environment": environment,
                    "repetition": rep,
                    "checkpoint_sha256": p["checkpoint_sha256"],
                    "incumbent": incumbent,
                    "candidate": name,
                    "candidate_is_different": name != incumbent,
                    "archived_C_trial_id": candidate["trial_id"],
                    "archived_C_request_sha256": candidate["request_sha256"],
                    "user_request": p["user_request"],
                    "prefix_name": p["prefix_name"],
                    "prefix_observation": p["prefix_observation"],
                    "state": sorted(set(p["state"])),
                    "goal_type": p["goal_type"],
                    "incumbent_suffix": p["incumbent_suffix"],
                    "tool_interfaces": p["tool_interfaces"],
                }
                rows.append(row)
    if len(rows) != 32 or sum(r["candidate_is_different"] for r in rows) != 16:
        raise ValueError("Expected 32 archived choices, 16 independent candidate deviations")
    return rows, indexed, cb


def gate_messages(row):
    if not row["candidate_is_different"]:
        raise ValueError("No gate needed for identical proposal")
    message = (
        "Original user request:\n" + row["user_request"]
        + "\n\nCompleted prefix tool: " + str(row["prefix_name"])
        + "\nObserved result: " + str(row["prefix_observation"])
        + "\nAvailable state types: " + ", ".join(row["state"])
        + "\nGoal output type: " + str(row["goal_type"])
        + "\nExisting remaining plan from before environment update: "
        + " -> ".join(row["incumbent_suffix"])
        + "\n\nIndependent next-action proposal, generated without seeing that plan: "
        + row["candidate"]
        + "\n\nYou must decide whether to KEEP the incumbent first action or ACCEPT "
        "the independently proposed next action. Both are executable at this checkpoint. "
        "Use the current native tool definitions and evaluate feasible remaining paths "
        "to the goal, not just immediate tool properties. "
        "ACCEPT only if the proposed action offers a clearly better feasible continuation. "
        "Otherwise KEEP, including when evidence is inconclusive. "
        "The proposed action is not necessarily correct. Do not call a tool; respond with "
        "only a JSON object containing decision set to KEEP or ACCEPT, and a short reason."
        + "\n\nCurrent native tool definitions:\n"
        + json.dumps(row["tool_interfaces"], ensure_ascii=False, sort_keys=True)
    )
    return [
        {"role": "system", "content": "You are reviewing a single next-action decision at a frozen tool-use checkpoint. Return only JSON; do not invoke tools."},
        {"role": "user", "content": message},
    ]


def extract_decision(content):
    try:
        obj = json.loads(content or "")
        decision = obj.get("decision")
        return decision if decision in {"KEEP", "ACCEPT"} else None
    except (TypeError, ValueError, AttributeError):
        return None


def summarize(records):
    cells = defaultdict(list)
    for r in records:
        cells[r["environment"]].append(r)
    table = {}
    for env in ("RETAIN", "SWITCH"):
        rs = cells[env]
        table[env] = {
            "checkpoints": len(rs),
            "optimal_first_actions": sum(x.get("selected_is_optimal") is True for x in rs),
            "accepted_alternative": sum(x.get("decision") == "ACCEPT" for x in rs),
            "candidate_different": sum(x.get("candidate_is_different") for x in rs),
            "unresolved_or_failed": sum(x.get("error") is not None or x.get("decision") is None for x in rs),
        }
    accuracy = {env: table[env]["optimal_first_actions"] / table[env]["checkpoints"] for env in table}
    return {
        "by_environment": table,
        "balanced_accuracy": (accuracy["RETAIN"] + accuracy["SWITCH"]) / 2,
        "task_results": [
            {"query_id": r["query_id"], "environment": r["environment"],
             "repetition": r["repetition"], "decision": r["decision"],
             "selected": r["selected_tool"], "optimal": r["selected_is_optimal"]}
            for r in sorted(records, key=lambda x: (x["query_id"], x["environment"], x["repetition"]))
        ],
    }


async def run(rows, indexed, out, token_cap, max_tokens):
    from openai import AsyncOpenAI
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY unavailable; no billable calls made")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Results path already occupied: {out}")
    out.mkdir(parents=True, exist_ok=True)
    budget = screen.native.TokenBudget(token_cap)
    records = []
    async with AsyncOpenAI(base_url="https://api.deepseek.com", api_key=key, timeout=120) as client:
        for row in rows:
            p = indexed[(row["query_id"], row["environment"])][1]
            result = {k: row[k] for k in ("query_id", "environment", "repetition",
                "checkpoint_sha256", "incumbent", "candidate", "candidate_is_different",
                "archived_C_trial_id", "archived_C_request_sha256")}
            result["decision"] = "KEEP"
            result["error"] = None
            if row["candidate_is_different"]:
                messages = gate_messages(row)
                reserve = screen.native.reservation_for_call(messages, row["tool_interfaces"], max_tokens)
                if not budget.can_call(reserve):
                    raise RuntimeError("Gate token reservation cap reached")
                budget.reserved += reserve
                screen.append_jsonl(out / "gate_requests.jsonl", {
                    "checkpoint": result, "messages": messages, "max_tokens": max_tokens,
                    "sha256": stable_sha(messages),
                })
                try:
                    response = await client.chat.completions.create(
                        model=screen.native.MODEL,
                        messages=messages, temperature=0, max_tokens=max_tokens,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    budget.record_usage(response.usage)
                    result["provider_tokens"] = int(response.usage.total_tokens)
                    result["model_response"] = response.choices[0].message.content
                    decision = extract_decision(result["model_response"])
                    if decision:
                        result["decision"] = decision
                    else:
                        result["error"] = "invalid_json_decision_fallback_keep"
                except Exception as exc:
                    result["error"] = f"{type(exc).__name__}: {exc}"
                    result["decision"] = "KEEP"
                    result["provider_tokens"] = 0
            selected = row["candidate"] if result["decision"] == "ACCEPT" else row["incumbent"]
            _, values, optimal = screen.optimal_first_actions(p)
            if selected not in values:
                raise ValueError("Gate selected a native-infeasible tool")
            result["selected_tool"] = selected
            result["selected_is_optimal"] = selected in optimal
            result["candidate_is_optimal"] = row["candidate"] in optimal
            result["incumbent_is_optimal"] = row["incumbent"] in optimal
            result["accounted_tokens"] = budget.charged
            records.append(result)
            screen.append_jsonl(out / "gate_responses.jsonl", result)
            screen.save_json(out / "summary.json", {
                "status": "in_progress", "completed": len(records), "total": len(rows),
                "charged_tokens": budget.charged, **summarize(records)
            }) if len(records)==len(rows) else None
            print(json.dumps({"checkpoint": len(records), "of":len(rows), "task":row["query_id"],
                              "environment":row["environment"],"decision":result["decision"],
                              "tokens":budget.charged}), flush=True)
            if result["error"] and result["error"].startswith(("API", "Runtime", "Timeout")):
                break
    if len(records)==len(rows):
        summary = {"status": "complete", "completed":len(records),
                   "total":len(rows), "charged_tokens":budget.charged,
                   "token_cap":token_cap, "model":screen.native.MODEL,
                   "independent_base_tasks":8, "new_provider_calls":sum(x["candidate_is_different"] for x in records),
                   "archived_C_generation_reused":True, **summarize(records)}
    else:
        summary = {"status":"incomplete","completed":len(records),"total":len(rows),
                   "charged_tokens":budget.charged, **summarize(records)}
    screen.save_json(out / "summary.json", summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--costbench-root", required=True, type=Path)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "counterfactual_gate_results")
    ap.add_argument("--cap", type=int, default=250000)
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    data_dir = (HERE.parent / "generated").resolve()
    rows, indexed, _ = prepare(args.archive.resolve(), args.costbench_root.resolve(), data_dir)
    audit = {
        "status": "offline_preflight", "base_tasks":8, "checkpoints":len(rows),
        "candidate_deviations":sum(r["candidate_is_different"] for r in rows),
        "candidate_provenance":"four-arm archived C action",
        "oracle_in_prompts":False, "new_provider_calls":0
    }
    if not args.live:
        print(json.dumps(audit, indent=2))
        return
    result = asyncio.run(run(rows,indexed,args.out.resolve(),args.cap,args.max_tokens))
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if result["status"]!="complete":
        raise SystemExit(2)


if __name__=="__main__":
    main()
