import unittest

from run_counterfactual_gate import extract_decision, gate_messages, summarize


class CounterfactualGateTests(unittest.TestCase):
    def test_decision_parser_accepts_only_known_values(self):
        self.assertEqual(extract_decision('{"decision":"ACCEPT","reason":"better"}'), "ACCEPT")
        self.assertEqual(extract_decision('{"decision":"KEEP"}'), "KEEP")
        self.assertIsNone(extract_decision('{"decision":"SWITCH"}'))
        self.assertIsNone(extract_decision('not json'))

    def test_gate_uses_old_plan_and_unguided_candidate(self):
        row = {
            "candidate_is_different": True,
            "user_request": "Complete journey.",
            "prefix_name": "search",
            "prefix_observation": "data",
            "state": ["Location"],
            "goal_type": "Final",
            "incumbent_suffix": ["old", "finish"],
            "candidate": "alternative",
            "tool_interfaces": [
                {"type": "function", "function": {
                    "name": "alternative", "description": "available"}},
                {"type": "function", "function": {
                    "name": "old", "description": "available"}},
            ],
        }
        prompt = gate_messages(row)
        self.assertIn("Existing remaining plan", prompt[1]["content"])
        self.assertIn("Independent next-action proposal", prompt[1]["content"])
        self.assertIn("old -> finish", prompt[1]["content"])
        self.assertNotIn("oracle_optimal", prompt[1]["content"])
        self.assertNotIn("RETAIN", prompt[1]["content"])
        self.assertNotIn("SWITCH", prompt[1]["content"])

    def test_summary_balanced_accuracy_is_not_raw_switch_rate(self):
        rows = [
            {"query_id": "a", "environment": "RETAIN", "repetition": 1,
             "decision": "KEEP", "selected_tool": "old",
             "selected_is_optimal": True, "candidate_is_different": True,
             "error": None},
            {"query_id": "b", "environment": "SWITCH", "repetition": 1,
             "decision": "ACCEPT", "selected_tool": "new",
             "selected_is_optimal": True, "candidate_is_different": True,
             "error": None},
        ]
        result = summarize(rows)
        self.assertEqual(result["balanced_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
