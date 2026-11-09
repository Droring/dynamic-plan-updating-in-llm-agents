"""Verify the documented candidate allocation preserves screened development tasks.

Runs without CostBench checkout, model API or graph solver. A failure here
blocks publication of a mutated or contaminated heldout partition.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/costbench_method_studies/candidate_source_registry"
ALLOCATION = ROOT / "research/costbench_method_studies/official_native_task_allocation"
spec = importlib.util.spec_from_file_location("candidate_allocation", ALLOCATION / "build_allocation.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def load_rows(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


class CandidateAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = load_rows(SOURCE / "generated/candidate_registry.jsonl")
        cls.rows, cls.report = mod.build()

    def test_exact_deterministic_committed_artifact(self):
        mod.write_or_check(self.rows, self.report, check=True)
        self.assertEqual(len(self.rows), 200)
        self.assertEqual(self.report["schema"], "costbench-candidate-allocation-80-40-80")
        self.assertEqual(self.report["target_split_counts"], {
            "development": 80, "validation": 40, "locked_test": 80
        })
        self.assertFalse(self.report["task_source_or_gold_read"])
        self.assertFalse(self.report["validation_test_graph_read"])
        self.assertEqual(self.report["model_or_native_calls"], 0)

    def test_same_200_task_ids_signatures_source_hashes_and_order(self):
        original_by_id = {x["query_id"]:x for x in self.original}
        self.assertEqual(
            [x["query_id"] for x in self.rows],
            [x["query_id"] for x in self.original]
        )
        self.assertEqual(len({x["query_id"] for x in self.rows}),200)
        self.assertEqual(len({x["preference_sha256"] for x in self.rows}),200)
        for row in self.rows:
            src=original_by_id[row["query_id"]]
            self.assertEqual(
                {k:v for k,v in row.items() if k!="split"},
                {k:v for k,v in src.items() if k!="split"}
            )
            self.assertEqual(set(row),set(src))

    def test_25_already_observed_development_cases_cannot_escape(self):
        known = {x["query_id"] for x in self.original if x["split"]=="development"}
        updated = {x["query_id"] for x in self.rows if x["split"]=="development"}
        self.assertEqual(len(known),25)
        self.assertTrue(known.issubset(updated))
        # The old dev graph, native tool and event reports must ALL have IDs
        # exclusively in current development. No old result can leak to test.
        g=json.loads((SOURCE/"generated/DEV_GRAPH_GATE.json").read_text(encoding="utf-8"))
        native=json.loads((SOURCE/"generated/DEV_NATIVE_ALL.json").read_text(encoding="utf-8"))
        labels=json.loads((SOURCE/"generated/DEV_EVENT_LABELS.json").read_text(encoding="utf-8"))
        self.assertEqual({x["query_id"] for x in g["development_cases"]},known)
        self.assertEqual({x["query_id"] for x in native["cases"]},known)
        self.assertEqual({x["query_id"] for x in labels["labels"]},known)
        self.assertTrue(known.isdisjoint({x["query_id"] for x in self.rows
                                         if x["split"] in ("validation","locked_test")}))

    def test_reallocation_minimizes_unnecessary_heldout_churn(self):
        self.assertEqual(self.report["source_to_allocation_transition_counts"],{
            "development":{"development":25},
            "validation":{"development":10,"validation":40},
            "locked_test":{"development":45,"locked_test":80}
        })
        self.assertEqual(Counter(x["split"] for x in self.rows),{
            "development":80,"validation":40,"locked_test":80
        })
        for cat, counts in mod.TARGET.items():
            self.assertEqual(Counter(r["split"] for r in self.rows if r["category"]==cat),counts)
        old_val={x["query_id"] for x in self.original if x["split"]=="validation"}
        old_test={x["query_id"] for x in self.original if x["split"]=="locked_test"}
        new_val={x["query_id"] for x in self.rows if x["split"]=="validation"}
        new_test={x["query_id"] for x in self.rows if x["split"]=="locked_test"}
        self.assertTrue(new_val.issubset(old_val))
        self.assertTrue(new_test.issubset(old_test))
        self.assertEqual(len(new_val),40)
        self.assertEqual(len(new_test),80)

    def test_registry_contains_no_model_observations_or_hidden_labels(self):
        # The split registry is a dataset manifest, not an Agent Harness output.
        forbidden={"gold_action","oracle_cost","evaluation_optimal_suffix",
                   "observed_native_prefix","committed_remaining_plan",
                   "future_tool_results","completed_agent_trajectory"}
        for row in self.rows:
            self.assertTrue(forbidden.isdisjoint(row))
        self.assertEqual(self.report["target_split_counts"],{
            "development":80,"validation":40,"locked_test":80
        })
        self.assertFalse(self.report["task_source_or_gold_read"])
        self.assertFalse(self.report["validation_test_graph_read"])
        self.assertEqual(self.report["model_or_native_calls"],0)


if __name__ == "__main__":
    unittest.main()
