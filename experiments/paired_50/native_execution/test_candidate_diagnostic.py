import unittest

from prepare_candidate_diagnostic import deterministic_orders, make_prompt
from run_candidate_diagnostic import score_text, summarize


class CandidateDecisionDiagnosticTests(unittest.TestCase):
    def test_candidate_order_is_deterministic_and_reversed(self):
        first, second = deterministic_orders(["c", "a", "b"], "Query00188/SWITCH")
        self.assertEqual(sorted(first), ["a", "b", "c"])
        self.assertEqual(second, list(reversed(first)))
        self.assertEqual((first, second), deterministic_orders(["b", "c", "a"], "Query00188/SWITCH"))

    def test_text_prompt_removes_execution_instruction(self):
        prepared = {
            "incumbent_suffix": ["old"],
            "state": {"Start"},
            "prefix_name": "none",
            "prefix_observation": "ready",
            "user_request": "Find destination.",
            "goal_type": "Goal",
            "changed_tool": "old",
        }
        for endpoint in ("comparison", "execution"):
            prompt = make_prompt(prepared, endpoint, ["old", "new"])
            self.assertIn("new", prompt)
            self.assertNotIn("execute the task until the goal type", prompt)
        self.assertIn("do not call any tool", make_prompt(prepared, "consideration", None).lower())

    def test_text_choice_scoring_checks_feasibility(self):
        ref = {"optimal_first_actions": ["new"], "incumbent": "old"}
        good = score_text("comparison", '{"chosen_tool":"new"}', ref, {"new", "old"}, {"new", "old"})
        self.assertTrue(good["optimal_choice"])
        bad = score_text("comparison", '{"chosen_tool":"new"}', ref, {"new", "old"}, {"old"})
        self.assertFalse(bad["valid_choice"])
        malformed = score_text("consideration", '{"candidates":["new","new"]}', ref, {"new", "old"}, {"new", "old"})
        self.assertFalse(malformed["valid_candidates"])

    def test_consistency_matches_exact_checkpoint_and_order(self):
        base = {"query_id": "Query00188", "environment": "SWITCH", "order": 0}
        rows = [
            dict(base, endpoint="comparison", chosen_tool="new", optimal_choice=True, provider_tokens=20),
            dict(base, endpoint="execution", executed_tool="new", optimal_executed=True, provider_tokens=20),
        ]
        result = summarize(rows)
        self.assertEqual(result["consistency_pairs"], 1)
        self.assertEqual(result["consistency_matches"], 1)
        self.assertEqual(result["cells"]["SWITCH/execution"]["correct"], 1)


if __name__ == "__main__":
    unittest.main()
