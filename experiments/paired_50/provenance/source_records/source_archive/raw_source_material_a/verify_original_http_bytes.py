#!/usr/bin/env python3
"""Verify ORIGINAL provider HTTP response bytes for the 30-pair online run.

No network, API keys, model reruns, or reconstruction of missing provider bytes.
This is stricter than replaying response_text: every original HTTP .bin body
must be found, its hash must match the saved per-trial hash, and its parsed
content, usage, model and finish status must match the saved JSONL row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parents[6]
EVIDENCE = HERE / "experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a" / "evidence"
EXPECTED = 60


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _original_bin(root: Path, row: dict) -> Path:
    trial = row.get("trial_id")
    if not isinstance(trial, str) or len(trial) != 20 or not all(c in "0123456789abcdef" for c in trial):
        raise ValueError("invalid trial id")
    saved = row.get("raw_file")
    if not isinstance(saved, str) or PureWindowsPath(saved).name != trial + ".bin":
        raise ValueError("raw file name not linked to trial id " + trial)
    # Restrict discovery to the exact original layout. Never use untrusted
    # saved paths as arbitrary filesystem locations.
    base = root.resolve()
    options = [base / "raw" / (trial + ".bin"), base / (trial + ".bin")]
    available = [p for p in options if p.is_file() and p.resolve().is_relative_to(base)]
    if len(available) != 1:
        raise FileNotFoundError("missing or ambiguous original HTTP .bin for trial " + trial)
    return available[0]


def verify(root: Path, records: list[dict], manifest: list[dict], expected_count: int = EXPECTED) -> dict:
    if len(records) != expected_count or len(manifest) != expected_count:
        raise ValueError("record/manifest count mismatch")
    by_id = {r["trial_id"]: r for r in manifest}
    if len(by_id) != expected_count or len({r["trial_id"] for r in records}) != expected_count:
        raise ValueError("duplicate trial id")
    audit = []
    for row in records:
        trial = row["trial_id"]
        gold = by_id.get(trial)
        if gold is None or row["request_sha256"] != gold["request_sha256"] or row["query_id"] != gold["query_id"]:
            raise ValueError("frozen trial or request hash mismatch " + trial)
        path = _original_bin(root, row)
        raw = path.read_bytes()
        digest = sha256(raw)
        if digest != row.get("raw_sha256"):
            raise ValueError("PROVIDER-BYTE HASH MISMATCH " + trial)
        try:
            response = json.loads(raw)
            choice = response["choices"][0]
            returned = choice["message"]["content"]
            usage = response["usage"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ValueError("invalid original provider HTTP response " + trial) from exc
        if returned != row.get("response_text"):
            raise ValueError("provider message differs from saved response_text " + trial)
        if choice.get("finish_reason") != row.get("finish_reason"):
            raise ValueError("provider finish_reason mismatch " + trial)
        if response.get("model") != row.get("model_reported"):
            raise ValueError("provider model mismatch " + trial)
        if usage != row.get("usage") or usage.get("total_tokens") != row.get("charged_tokens"):
            raise ValueError("provider usage mismatch " + trial)
        if row.get("error") is not None:
            raise ValueError("saved provider error " + trial)
        audit.append({"trial_id": trial, "query_id": row["query_id"], "sha256": digest, "size_bytes": len(raw)})
    audit.sort(key=lambda x: x["trial_id"])
    fingerprint = sha256(json.dumps(audit, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {
        "status": "all_original_http_bytes_verified",
        "verified": len(audit),
        "expected": expected_count,
        "original_http_byte_manifest_sha256": fingerprint,
        "records": audit,
        "limitation": "This verifies that available saved provider bytes match previously recorded hashes; it does not independently attest provider identity or re-execute the model."
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="original live_results directory, or its raw/ subdirectory")
    parser.add_argument("--out", type=Path, default=None, help="optional machine-readable verification report")
    args = parser.parse_args()
    records = [json.loads(line) for line in (EVIDENCE / "online_60_responses.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads((HERE / "experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated/trial_manifest.json").read_text(encoding="utf-8"))
    result = verify(args.root, records, manifest)
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
