import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_four_arm_experiment import candidate_availability_audit, summarize


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

    def test_oracle_candidate_must_be_in_interface_and_feasible(self):
        tool = SimpleNamespace(cost=12.5, input_types={"A", "B"})
        prepared = {
            "checkpoint_sha256": "checkpoint",
            "state": {"A", "B"},
            "incumbent_suffix": ["OldTool"],
            "tool_objects": {"BestTool": tool},
            "tool_interfaces": [{"function": {"name": "BestTool"}}],
        }
        trial = {
            "query_id": "QueryTest",
            "environment_condition": "SWITCH",
            "prepared": prepared,
        }
        with patch(
            "run_four_arm_experiment.optimal_first_actions",
            return_value=(20.0, {"OldTool": 21.0, "BestTool": 20.0}, ["BestTool"]),
        ):
            result = candidate_availability_audit([trial])
        candidate = result[0]["oracle_optimal_first_actions"][0]
        self.assertTrue(candidate["available_in_interface"])
        self.assertTrue(candidate["feasible_from_checkpoint"])
        self.assertEqual(candidate["required_inputs"], ["A", "B"])
        self.assertEqual(result[0]["incumbent_is_optimal"], False)

    def test_oracle_candidate_missing_inputs_fails_audit(self):
        tool = SimpleNamespace(cost=12.5, input_types={"A", "Missing"})
        prepared = {
            "checkpoint_sha256": "checkpoint",
            "state": {"A"},
            "incumbent_suffix": ["OldTool"],
            "tool_objects": {"BestTool": tool},
            "tool_interfaces": [{"function": {"name": "BestTool"}}],
        }
        trial = {
            "query_id": "QueryTest",
            "environment_condition": "SWITCH",
            "prepared": prepared,
        }
        with patch(
            "run_four_arm_experiment.optimal_first_actions",
            return_value=(20.0, {"BestTool": 20.0}, ["BestTool"]),
        ):
            with self.assertRaisesRegex(ValueError, "infeasible"):
                candidate_availability_audit([trial])

    def test_incomplete_summary_is_not_marked_complete(self):
        result = summarize([], 16)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["attempted_trials"], 0)
        self.assertEqual(result["planned_trials"], 16)


if __name__ == "__main__":
    unittest.main()
