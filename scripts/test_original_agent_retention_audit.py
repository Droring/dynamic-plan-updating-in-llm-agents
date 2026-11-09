"""Regression tests for the original native Agent retention audit."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/costbench_method_studies/plan_commitment_evidence_gate/audit_original_agent_retention.py"
EVIDENCE = ROOT / "research/costbench_method_studies/plan_commitment_evidence_gate/evidence"


def load_module():
    spec = importlib.util.spec_from_file_location("original_agent_retention_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OriginalAgentRetentionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.data = cls.module.build_audit(ROOT)
        cls.committed = json.loads(
            (EVIDENCE / "ORIGINAL_AGENT_RETENTION_AUDIT.json").read_text(encoding="utf-8")
        )

    def test_population_and_prefix_integrity(self):
        summary = self.data["summary"]
        self.assertEqual(summary["official_development_tasks"], 80)
        self.assertEqual(summary["observed_dynamic_event_tasks"], 67)
        self.assertEqual(summary["valid_agent_authored_plan_tasks"], 27)
        self.assertEqual(summary["original_agent_behavior"]["pre_event_prefix_matches_agent_plan"], 27)

    def test_original_agent_first_actions_follow_incumbent(self):
        result = self.data["summary"]["original_agent_behavior"]
        self.assertEqual(result["first_action_follows_incumbent"], 27)
        self.assertEqual(result["first_action_matches_current_optimum"], 15)
        self.assertEqual(result["first_action_not_current_optimum"], 12)
        self.assertEqual(result["exact_incumbent_suffix"], 23)
        self.assertEqual(result["exact_current_optimal_suffix"], 15)

    def test_gate_switch_cases_are_not_model_switches(self):
        result = self.data["summary"]["gate_switch_subset"]
        self.assertEqual(result["n"], 5)
        self.assertEqual(result["first_action_follows_incumbent"], 5)
        self.assertEqual(result["first_action_matches_current_optimum"], 0)
        self.assertEqual(result["false_retain_first_actions"], 5)

    def test_original_goals_and_final_answers_are_distinct(self):
        result = self.data["summary"]["original_agent_behavior"]
        self.assertEqual(result["goal_reached"], 27)
        self.assertEqual(result["official_final_answer_accepted"], 24)

    def test_committed_audit_matches_recomputation(self):
        self.assertEqual(self.data, self.committed)
        self.assertEqual(
            (EVIDENCE / "ORIGINAL_AGENT_RETENTION_AUDIT.csv").read_text(encoding="utf-8"),
            self.module.render_csv(self.data),
        )


if __name__ == "__main__":
    unittest.main()
