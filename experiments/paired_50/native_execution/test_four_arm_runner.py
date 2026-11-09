import unittest

from run_four_arm_experiment import summarize


class FourArmRunnerTests(unittest.TestCase):
    def test_summary_keeps_no_action_and_invalid_actions_in_denominator(self):
        rows = [
            {
                "environment_condition": "SWITCH",
                "prompt_condition": "A",
                "first_action_status": "executed",
                "first_action_regret": 0.0,
                "is_optimal_first_action": True,
                "first_action_is_incumbent": False,
            },
            {
                "environment_condition": "SWITCH",
                "prompt_condition": "A",
                "first_action_status": "no_tool_call",
                "first_action_regret": None,
            },
            {
                "environment_condition": "SWITCH",
                "prompt_condition": "A",
                "first_action_status": "missing_inputs",
                "first_action_regret": None,
            },
        ]
        result = summarize(rows, 3)
        cell = result["cell_summary"]["SWITCH/A"]
        self.assertEqual(result["status"], "complete")
        self.assertEqual(cell["attempted"], 3)
        self.assertEqual(cell["valid_executions"], 1)
        self.assertEqual(cell["optimal_first_actions"], 1)
        self.assertEqual(cell["no_tool_call"], 1)
        self.assertEqual(cell["invalid_or_missing"], 1)

    def test_incomplete_summary_is_not_marked_complete(self):
        result = summarize([], 16)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["attempted_trials"], 0)
        self.assertEqual(result["planned_trials"], 16)


if __name__ == "__main__":
    unittest.main()
