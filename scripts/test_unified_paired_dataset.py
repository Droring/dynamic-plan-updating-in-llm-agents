"""Integrity tests for the canonical unified 50-task paired benchmark."""
import hashlib
import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments" / "paired_50"
DATA = BASE / "generated"

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class UnifiedPairedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_json(DATA / "task_registry_50.json")
        cls.manifest = load_json(DATA / "trial_manifest_100.json")
        cls.pairs = load_json(DATA / "pairs_50.json")["pairs"]
        cls.requests = [json.loads(x) for x in (DATA / "model_requests_100.jsonl").read_text(encoding="utf-8").splitlines() if x]
        cls.scores = load_json(BASE / "live_results" / "deepseek-flash" / "scores.json")

    def test_registry_and_category_balance(self):
        self.assertEqual(self.registry["base_task_count"], 50)
        self.assertEqual(self.registry["condition_count"], 100)
        self.assertEqual(len(self.registry["selection"]["task_ids"]), 50)
        self.assertEqual(self.registry["categories"], {
            "transportation": 10, "accommodation": 10, "attraction": 10,
            "dining": 10, "shopping": 10
        })

    def test_every_task_has_one_matched_pair(self):
        records = self.manifest["records"]
        self.assertEqual(len(records), 100)
        self.assertEqual(len({x["trial_id"] for x in records}), 100)
        groups = defaultdict(list)
        for row in records:
            groups[row["query_id"]].append(row)
        self.assertEqual(len(groups), 50)
        for rows in groups.values():
            self.assertEqual({x["condition"] for x in rows}, {"RETAIN", "SWITCH"})
            self.assertEqual(len({x["checkpoint_sha256"] for x in rows}), 1)

    def test_frozen_request_hashes_and_manifest(self):
        self.assertEqual(len(self.requests), 100)
        by_id = {x["trial_id"]: x for x in self.requests}
        self.assertEqual(len(by_id), 100)
        manifest = {x["trial_id"]: x for x in self.manifest["records"]}
        self.assertEqual(set(by_id), set(manifest))
        for tid, request in by_id.items():
            self.assertEqual(digest(request), manifest[tid]["request_sha256"])
            self.assertEqual(request["query_id"], manifest[tid]["query_id"])
            self.assertEqual(request["checkpoint_sha256"], manifest[tid]["checkpoint_sha256"])

    def test_pair_fixture_matches_registry(self):
        self.assertEqual(len(self.pairs), 50)
        registry_ids = [x["task_id"] for x in self.registry["selection"]["task_ids"]]
        self.assertEqual([x["query_id"] for x in self.pairs], registry_ids)
        self.assertEqual(len({x["checkpoint_sha256"] for x in self.pairs}), 50)

    def test_scored_outputs_match_protocol_counts(self):
        self.assertEqual(self.scores["status"], "complete")
        self.assertEqual((self.scores["base_tasks"], self.scores["attempted"]), (50, 100))
        self.assertEqual((self.scores["retain"]["correct"], self.scores["switch"]["correct"]), (48, 3))
        self.assertEqual(self.scores["pair_correct"], 1)
        self.assertEqual(self.scores["input_sha256"], "a3f368ee12b7edc6fdea1fa6da90779a93c3e8c5b1d57309876784268d56c9e7")
        self.assertEqual(self.scores["manifest_sha256"], "ef1470f06191ce2d8792da8034dc6e1225d6ddda4f6bb5c29cae6a642579a8c8")

if __name__ == "__main__":
    unittest.main()
