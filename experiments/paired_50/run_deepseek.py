#!/usr/bin/env python3
"""One-shot, paid 100-condition DeepSeek evaluation of frozen paired CostBench requests.

No automatic retries or resumed billing; provider replies and hashes are archived.
The dataset and scorer must not depend on previous model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "generated"
API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
OUTPUT_TOKENS = 96
BUFFER_TOKENS = 512
RESPONSE_BYTE_CAP = 3_000_000


def canonical_sha(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_frozen():
    requests = [json.loads(line) for line in (DATA / "model_requests_100.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads((DATA / "trial_manifest_100.json").read_text(encoding="utf-8"))["records"]
    registry = json.loads((DATA / "task_registry_50.json").read_text(encoding="utf-8"))
    if len(requests) != len(manifest) or len(requests) != 100 or registry["base_task_count"] != 50:
        raise ValueError("100-condition frozen input count mismatch")
    by_id = {r["trial_id"]: r for r in manifest}
    if len(by_id) != 100 or len({r["trial_id"] for r in requests}) != 100:
        raise ValueError("duplicate trial IDs")
    counts = Counter()
    groups = defaultdict(list)
    systems = set()
    for i, req in enumerate(requests):
        tid = req["trial_id"]
        row = by_id.get(tid)
        if not row or canonical_sha(req) != row["request_sha256"]:
            raise ValueError("mismatched frozen request hash")
        if req["query_id"] != row["query_id"] or req["checkpoint_sha256"] != row["checkpoint_sha256"]:
            raise ValueError("checkpoint mismatch")
        if set(req) != {"trial_id", "query_id", "checkpoint_sha256", "messages", "response_format"}:
            raise ValueError("unexpected request fields")
        if req["response_format"] != {"type": "json_object"}:
            raise ValueError("response format mismatch")
        if [m["role"] for m in req["messages"]] != ["system", "user"]:
            raise ValueError("unexpected chat history")
        visible = json.loads(req["messages"][-1]["content"])
        if any(k in visible for k in ("condition", "oracle_cost", "regret", "gold_label", "correct_answer")):
            raise ValueError("gold information visible in model prompt")
        if visible.get("task_id") != req["query_id"]:
            raise ValueError("task ID mismatch")
        systems.add(req["messages"][0]["content"])
        counts[row["condition"]] += 1
        groups[req["query_id"]].append(row)
        if i % 2 == 0 and i + 1 < 100 and requests[i + 1]["query_id"] != req["query_id"]:
            raise ValueError("paired requests not contiguous")
    if counts != {"RETAIN": 50, "SWITCH": 50} or len(systems) != 1 or len(groups) != 50:
        raise ValueError("unbalanced or nonuniform requests")
    for rows in groups.values():
        if len(rows) != 2 or {r["condition"] for r in rows} != {"RETAIN", "SWITCH"}:
            raise ValueError("unpaired labels")
        if len({r["checkpoint_sha256"] for r in rows}) != 1:
            raise ValueError("unmatched checkpoints")
    return requests, by_id


def payload(req):
    return {"model": MODEL, "messages": req["messages"],
            "response_format": req["response_format"],
            "thinking": {"type": "disabled"},
            "temperature": 0, "max_tokens": OUTPUT_TOKENS, "stream": False}


def reserve_tokens(p):
    # Conservative UTF-8 bytes proxy with output and accounting buffer.
    return len(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + OUTPUT_TOKENS + BUFFER_TOKENS


def label(text):
    if not isinstance(text, str):
        return None
    try:
        def nodup(pairs):
            obj = {}
            for k, v in pairs:
                if k in obj:
                    raise ValueError("duplicate JSON key")
                obj[k] = v
            return obj
        obj = json.loads(text, object_pairs_hook=nodup)
        if isinstance(obj, dict) and set(obj) == {"intervention"} and obj["intervention"] in ("RETAIN", "SWITCH"):
            return obj["intervention"]
    except (ValueError, TypeError):
        pass
    return None


def grade(records, manifest):
    seen = {}
    for record in records:
        tid = record.get("trial_id")
        if tid not in manifest or tid in seen or record.get("request_sha256") != manifest[tid]["request_sha256"]:
            raise ValueError("unknown, duplicated or altered provider record")
        seen[tid] = record
    cm = {"RETAIN": Counter(), "SWITCH": Counter()}
    pairs = defaultdict(dict)
    tokens = 0
    for tid, row in manifest.items():
        record = seen.get(tid)
        if record is None:
            continue
        if record.get("usage") and isinstance(record["usage"].get("total_tokens"), int):
            tokens += record["usage"]["total_tokens"]
        prediction = label(record.get("response_text"))
        truth = row["condition"]
        cm[truth]["total"] += 1
        if prediction is None:
            cm[truth]["invalid"] += 1
        else:
            cm[truth]["valid"] += 1
            cm[truth]["correct"] += int(prediction == truth)
        pairs[row["query_id"]][truth] = prediction
    complete = len(seen) == 100 and all(v["total"] == 50 for v in cm.values())
    pair_correct = sum(len(x) == 2 and x.get("RETAIN") == "RETAIN" and x.get("SWITCH") == "SWITCH" for x in pairs.values())
    return {"status": "complete" if complete else "incomplete", "attempted": len(seen),
            "total_conditions": 100, "base_tasks": 50,
            "retain": dict(cm["RETAIN"]), "switch": dict(cm["SWITCH"]),
            "pair_correct": pair_correct, "pair_accuracy": pair_correct / 50 if complete else None,
            "balanced_accuracy": (cm["RETAIN"]["correct"] + cm["SWITCH"]["correct"]) / 100 if complete else None,
            "provider_total_tokens": tokens, "invalid_predictions_count": cm["RETAIN"]["invalid"] + cm["SWITCH"]["invalid"]}


def call_once(p, key, timeout):
    raw = json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(API, data=raw, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(RESPONSE_BYTE_CAP + 1)
        if len(body) > RESPONSE_BYTE_CAP:
            return None, body[:RESPONSE_BYTE_CAP], {"kind": "oversized_response"}
        try:
            return json.loads(body), body, None
        except (ValueError, UnicodeDecodeError):
            return None, body, {"kind": "invalid_provider_json"}
    except urllib.error.HTTPError as error:
        return None, error.read(2000), {"kind": "http_error", "status": error.code}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, b"", {"kind": "network_or_timeout", "exception": type(error).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Explicitly authorize billable API calls")
    parser.add_argument("--cap", type=int, default=800000)
    parser.add_argument("--timeout", type=int, default=75)
    parser.add_argument("--out", type=Path, default=HERE / "live_results" / "deepseek-flash")
    args = parser.parse_args()
    requests, manifest = load_frozen()
    reservations = [reserve_tokens(payload(r)) for r in requests]
    total_reservation = sum(reservations)
    specs = {"model": MODEL, "model_calls_planned": 100,
             "input_sha256": sha_bytes((DATA / "model_requests_100.jsonl").read_bytes()),
             "manifest_sha256": sha_bytes((DATA / "trial_manifest_100.json").read_bytes()),
             "temperature": 0, "thinking": "disabled",
             "token_reservation": total_reservation, "token_cap": args.cap,
             "mode": "live" if args.live else "dry_run"}
    print(json.dumps(specs, indent=2), flush=True)
    if args.cap <= 0 or args.timeout <= 0 or total_reservation > args.cap:
        print("BLOCKED: conservative full-run token reservation exceeds cap", file=sys.stderr)
        return 4
    if not args.live:
        print("DRY RUN VALIDATED: 0 model API calls")
        return 0
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        print("BLOCKED: DEEPSEEK_API_KEY unavailable; zero model calls", file=sys.stderr)
        return 3
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError("Output directory nonempty: refusing duplicate paid run")
    args.out.mkdir(parents=True, exist_ok=True)
    rawdir = args.out / "raw"
    rawdir.mkdir()
    charged = 0
    records = []
    halt = None
    for req in requests:
        p = payload(req)
        estimate = reserve_tokens(p)
        if charged + estimate > args.cap:
            halt = "reservation_cap"
            break
        start = time.monotonic()
        answer, reply_bytes, error = call_once(p, key, args.timeout)
        usage = answer.get("usage") if isinstance(answer, dict) else None
        choices = answer.get("choices") if isinstance(answer, dict) else None
        choices = choices or []
        choice = choices[0] if len(choices) == 1 else {}
        finish = choice.get("finish_reason")
        message = choice.get("message") or {}
        content = message.get("content")
        if error is None and (not isinstance(usage, dict) or not isinstance(usage.get("total_tokens"), int)):
            error = {"kind": "missing_provider_usage"}
        if error is None and finish != "stop":
            error = {"kind": "abnormal_finish", "finish_reason": finish}
        if error is None and not isinstance(content, str):
            error = {"kind": "missing_content"}
        charge = usage["total_tokens"] if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int) else estimate
        charged += charge
        rawpath = rawdir / (req["trial_id"] + ".bin")
        rawpath.write_bytes(reply_bytes)
        record = {"trial_id": req["trial_id"], "query_id": req["query_id"],
                  "request_sha256": canonical_sha(req), "response_text": content, "usage": usage,
                  "model_requested": MODEL, "model_reported": answer.get("model") if isinstance(answer, dict) else None,
                  "finish_reason": finish, "system_fingerprint": answer.get("system_fingerprint") if isinstance(answer, dict) else None,
                  "error": error, "raw_sha256": sha_bytes(reply_bytes), "raw_file": "raw/" + rawpath.name,
                  "elapsed_seconds": round(time.monotonic() - start, 3), "charged_tokens": charge,
                  "reserved_tokens": estimate}
        records.append(record)
        with (args.out / "responses.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        (args.out / "ledger.json").write_text(json.dumps({
            "status": "in_progress", "attempted": len(records), "charged_tokens": charged,
            "cap": args.cap, "input_sha256": specs["input_sha256"]}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"trial": len(records), "charged": charge, "total": charged,
                          "error": error["kind"] if error else None}), flush=True)
        if error is not None:
            halt = error["kind"]
            break
        if charged > args.cap:
            halt = "usage_exceeded_cap"
            break
    result = grade(records, manifest)
    result.update({"halt_reason": halt, "reserved_full_run_tokens": total_reservation,
                   "token_cap": args.cap, "accounted_tokens": charged, "input_sha256": specs["input_sha256"],
                   "manifest_sha256": specs["manifest_sha256"], "no_retries": True})
    (args.out / "scores.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.out / "ledger.json").write_text(json.dumps({
        "status": result["status"], "attempted": len(records), "charged_tokens": charged,
        "cap": args.cap, "halt_reason": halt, "input_sha256": specs["input_sha256"]
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "complete" and halt is None else 2


if __name__ == "__main__":
    sys.exit(main())
