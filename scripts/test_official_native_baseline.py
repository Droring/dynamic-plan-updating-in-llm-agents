"""Official native 80-task evidence regression: provenance, split isolation, and report reproduction."""
from __future__ import annotations
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PHASE=ROOT/"research/costbench_method_studies/official_dev_baseline"
EVIDENCE=PHASE/"evidence"

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

class OfficialNativeBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit=load_module("official_native_audit",PHASE/"audit.py")
        cls.report=load_module("official_native_report",PHASE/"render_report.py")
        cls.doc=json.loads((EVIDENCE/"SUMMARY.json").read_text(encoding="utf-8"),
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonstandard JSON constant: "+x)))
        cls.manifest=json.loads((EVIDENCE/"inputs/manifest.json").read_text(encoding="utf-8"))
        cls.registry=[json.loads(line) for line in (ROOT/"research/costbench_method_studies/official_native_task_allocation/generated/candidate_registry.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_population_and_sealed_task_membership(self):
        self.assertEqual(len(self.registry),200)
        dev={x["query_id"] for x in self.registry if x["split"]=="development"}
        held={x["query_id"] for x in self.registry if x["split"]!="development"}
        self.assertEqual(len(dev),80)
        self.assertEqual(len(held),120)
        self.assertEqual(set(self.manifest["source_query_sha256"]),dev)
        self.assertEqual({x["query_id"] for x in self.doc["rows"]},dev)
        self.assertFalse(held & set(self.manifest["source_query_sha256"]))
        self.assertEqual(self.doc["independent_base_tasks"],80)
        self.assertEqual(len(self.doc["rows"]),160)

    def test_overlap_with_primary_50_tasks_is_explicit_and_bounded(self):
        paired=json.loads((ROOT/"experiments/paired_50/generated/task_registry_50.json").read_text(encoding="utf-8"))
        paired_ids={x["task_id"] for x in paired["selection"]["task_ids"]}
        development={x["query_id"] for x in self.registry if x["split"]=="development"}
        self.assertEqual(len(paired_ids),50)
        self.assertEqual(len(development),80)
        self.assertEqual(paired_ids & development,{"Query00499"})

    def test_all_eight_official_outputs_reproduce_audit(self):
        regenerated=self.audit.summarize(EVIDENCE)
        self.assertEqual(self.doc,regenerated)
        self.assertEqual(len(regenerated["raw_sha256"]),8)
        self.assertEqual(regenerated["per_condition"]["static"]["attempted_trajectories"],80)
        self.assertEqual(regenerated["per_condition"]["official_cost_change"]["attempted_trajectories"],80)

    def test_early_stops_are_not_collapsed_into_cost_event_failures(self):
        dyn=self.doc["per_condition"]["official_cost_change"]
        categories=dyn["pre_event_termination_types"]
        self.assertEqual(sum(categories.values()),dyn["dynamic_event_not_triggered"])
        self.assertEqual(dyn["dynamic_event_triggered"]+dyn["dynamic_event_not_triggered"],80)
        self.assertTrue(all(x["pre_event_termination"] is None or x["dynamic_events_triggered"]==0
            for x in self.doc["rows"]))

    def test_report_is_fully_reproducible(self):
        generated=self.report.render(self.doc)
        expected=(PHASE/"RESULTS.md").read_text(encoding="utf-8")
        self.assertEqual(generated,expected)
        self.assertIn("13/80",expected)
        self.assertIn("70/80",expected)
        self.assertIn("60/80",expected)

if __name__=="__main__":
    unittest.main()
