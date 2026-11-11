from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def read_jsonl(relative_path):
    return [
        json.loads(line)
        for line in (ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class IndependentValidationManifestTests(unittest.TestCase):
    def test_twenty_task_validation_cohort_is_stratified_and_disjoint(self):
        manifest = read_json(
            "research/complete_candidate_verification/INDEPENDENT_VALIDATION_TASK_MANIFEST.json"
        )
        allocation = read_json(
            "research/costbench_method_studies/official_native_task_allocation/generated/ALLOCATION_REPORT.json"
        )
        registry = read_jsonl(
            "research/costbench_method_studies/official_native_task_allocation/generated/candidate_registry.jsonl"
        )
        paired = read_json("experiments/paired_50/generated/task_registry_50.json")
        baseline = read_json(
            "research/costbench_method_studies/official_dev_baseline/evidence/inputs/manifest.json"
        )
        development = read_json(
            "research/complete_candidate_verification/DEVELOPMENT_SCREEN_MANIFEST.json"
        )
        four_arm = read_json(
            "experiments/paired_50/native_execution/FOUR_ARM_TASK_MANIFEST.json"
        )

        self.assertEqual(manifest["status"], "selected_not_executed")
        self.assertEqual(manifest["source"]["upstream_revision"],
                         "6424069f3f773ade076bcedbed302ed47cfb1837")
        self.assertEqual(
            manifest["source"]["allocated_registry_canonical_sha256"],
            allocation["allocated_registry_canonical_sha256"],
        )

        selected = manifest["selection"]["tasks"]
        self.assertEqual(len(selected), 20)
        selected_ids = [item["query_id"] for item in selected]
        self.assertEqual(len(set(selected_ids)), 20)
        self.assertEqual(
            Counter(item["category"] for item in selected),
            Counter({name: 4 for name in (
                "transportation", "accommodation", "attraction", "dining", "shopping"
            )}),
        )

        validation_rows = [item for item in registry if item["split"] == "validation"]
        expected_ids = []
        for category in ("transportation", "accommodation", "attraction", "dining", "shopping"):
            expected_ids.extend([
                item["query_id"] for item in validation_rows
                if item["category"] == category
            ][:4])
        self.assertEqual(selected_ids, expected_ids)

        by_id = {item["query_id"]: item for item in registry}
        for item in selected:
            source = by_id[item["query_id"]]
            self.assertEqual(source["split"], "validation")
            self.assertEqual(source["category"], item["category"])
            self.assertEqual(source["source_query_sha256"], item["source_query_sha256"])
            self.assertEqual(source["preference_sha256"], item["preference_sha256"])

        paired_ids = {item["task_id"] for item in paired["selection"]["task_ids"]}
        baseline_ids = {
            query_id for shard in baseline["shards"].values() for query_id in shard
        }
        development_ids = {
            item["query_id"] for item in development["selection"]["tasks"]
        }
        four_arm_ids = {item["query_id"] for item in four_arm["tasks"]}
        selected_set = set(selected_ids)
        self.assertFalse(selected_set & paired_ids)
        self.assertFalse(selected_set & baseline_ids)
        self.assertFalse(selected_set & development_ids)
        self.assertFalse(selected_set & four_arm_ids)

        self.assertEqual(len({item["source_query_sha256"] for item in selected}), 20)
        self.assertEqual(len({item["preference_sha256"] for item in selected}), 20)
        self.assertEqual(manifest["experiment"]["planned_native_trajectories"], 280)
        self.assertEqual(len(manifest["experiment"]["methods"]), 7)
        self.assertEqual(manifest["experiment"]["conditions"], ["RETAIN", "SWITCH"])
        self.assertEqual(manifest["independence_audit"]["provider_calls_during_selection"], 0)
        self.assertEqual(manifest["checkpoint_construction"]["status"], "pending_protocol_freeze")
        self.assertEqual(manifest["future_test"]["status"], "sealed_not_selected")


if __name__ == "__main__":
    unittest.main()
