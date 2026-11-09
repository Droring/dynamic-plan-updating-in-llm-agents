"""Regression for the frozen CostBench candidate selection and development gate."""
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/"research/costbench_method_studies/candidate_source_registry"
sys.path.insert(0,str(HERE))
from build_registry import QUOTAS, digest


class FrozenCandidateSelectionTests(unittest.TestCase):
    def test_200_candidates_have_no_duplicate_ids_or_preferences(self):
        directory=HERE/"generated"
        path=directory/"candidate_registry.jsonl"
        desc=directory/"SCREENING_REPORT.json"
        self.assertTrue(path.is_file(),"registry must be frozen by offline Actions first")
        self.assertTrue(desc.is_file(),"screening report must be committed")
        rows=[json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
        report=json.loads(desc.read_text(encoding="utf-8"))
        self.assertEqual(len(rows),200)
        self.assertEqual(report["candidate_registry_sha256"],digest(rows))
        self.assertEqual(len({x["query_id"] for x in rows}),200)
        self.assertEqual(len({x["preference_sha256"] for x in rows}),200)
        self.assertEqual(Counter(x["split"] for x in rows),
                         {"development":25,"validation":50,"locked_test":125})
        for cat,quotas in QUOTAS.items():
            self.assertEqual(
                Counter(x["split"] for x in rows if x["category"]==cat),quotas)
        for row in rows:
            self.assertEqual(set(row),{
                "query_id","category","split","preference_sha256","source_query_sha256"})
        self.assertTrue(report["no_gold_labels_created"])
        self.assertTrue(report["no_graph_feasibility_claimed"])

    def test_only_development_graph_was_inspected(self):
        report=json.loads((HERE/"generated/DEV_GRAPH_GATE.json").read_text(encoding="utf-8"))
        self.assertEqual(report["development_candidates"],25)
        self.assertEqual(report["validation_and_test_queries_inspected"],0)
        self.assertEqual(report["model_calls"],0)
        dev={json.loads(s)["query_id"] for s in
             (HERE/"generated/candidate_registry.jsonl").read_text(encoding="utf-8").splitlines()
             if s and json.loads(s)["split"]=="development"}
        self.assertEqual(dev,{x["query_id"] for x in report["development_cases"]})
        self.assertEqual(len(report["development_cases"]),25)
        self.assertTrue(all(x["native_execution_verified"] is False for x in report["development_cases"]))

    def test_native_prefix_on_all_25_development_tasks(self):
        path=HERE/"generated/DEV_NATIVE_ALL.json"
        self.assertTrue(path.is_file(),"all-development native diagnostic missing")
        diag=json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(diag["development_tasks"],25)
        self.assertEqual(diag["provider_calls"],0)
        self.assertEqual(diag["validation_and_test_tasks_executed"],0)
        self.assertEqual(diag["native_prefix_success"],25)
        dev={json.loads(s)["query_id"] for s in
             (HERE/"generated/candidate_registry.jsonl").read_text(encoding="utf-8").splitlines()
             if s and json.loads(s)["split"]=="development"}
        self.assertEqual(dev,{x["query_id"] for x in diag["cases"]})
        self.assertTrue(all(c["native_success"] and c["checkpoint_observation_sha256"]
                            for c in diag["cases"]))

    def test_frozen_source_registry_excludes_hidden_agent_outcomes(self):
        records=[json.loads(line) for line in
                 (HERE/"generated/candidate_registry.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        allowed={"query_id","category","split","preference_sha256","source_query_sha256"}
        self.assertEqual(len(records),200)
        self.assertTrue(all(set(record)==allowed for record in records))
        report=json.loads((HERE/"generated/SCREENING_REPORT.json").read_text(encoding="utf-8"))
        self.assertTrue(report["no_gold_labels_created"])
        self.assertTrue(report["no_graph_feasibility_claimed"])


if __name__=="__main__":
    unittest.main()
