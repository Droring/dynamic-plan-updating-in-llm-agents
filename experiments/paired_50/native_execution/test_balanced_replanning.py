import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_balanced_replanning import (
    build_balanced_payload,
    feasible_first_tools,
    make_trials,
)


class BalancedReplanningTests(unittest.TestCase):
    def setUp(self):
        self.prepared = {
            "user_request": "Finish the task.",
            "incumbent_suffix": ["old"],
            "state": {"Start"},
            "prefix_name": "none",
            "prefix_observation": "done",
            "goal_type": "Goal",
            "changed_tool": "old",
            "task": {},
            "tool_objects": {
                "old": SimpleNamespace(cost=5.0, input_types={"Start"}),
                "alternative": SimpleNamespace(cost=4.0, input_types={"Start"}),
                "unavailable": SimpleNamespace(cost=1.0, input_types={"Missing"}),
            },
            "tool_interfaces": [
                {"type": "function", "function": {"name": "old"}},
                {"type": "function", "function": {"name": "alternative"}},
                {"type": "function", "function": {"name": "unavailable"}},
            ],
        }

    def test_feasible_menu_not_solver_ranked(self):
        self.assertEqual(
            feasible_first_tools(self.prepared),
            ["alternative", "old"],
        )

    @patch("run_balanced_replanning.benchmark.native.make_official_system_prompt", return_value="native")
    def test_comparison_and_menu_keep_plan_and_exclude_oracle(self, _prompt):
        for arm in ("comparison", "feasible_menu"):
            payload = build_balanced_payload(
                {"prepared": self.prepared, "prompt_condition": arm}, object(),
            )
            user = payload["messages"][1]["content"]
            self.assertIn("Existing remaining plan", user)
            self.assertIn("old", user)
            self.assertIn("Compare the full remaining continuations", user)
            self.assertNotIn("oracle", user.lower() if arm == "comparison" else user.replace("Non-oracle", ""))
            self.assertNotIn("SWITCH", user)
            self.assertNotIn("RETAIN", user)
            if arm == "feasible_menu":
                self.assertIn("alternative, old", user)
                self.assertNotIn("unavailable", user)

    def test_frozen_design_uses_both_conditions_and_two_repetitions(self):
        tasks = [{"query_id": f"Query{i:05d}", "category": "test"} for i in range(8)]
        selected = []
        for task in tasks:
            for condition in ("RETAIN", "SWITCH"):
                selected.append((
                    task, {"trial_id": task["query_id"] + condition},
                    {"condition": condition}, self.prepared
                ))
        trials = make_trials(selected, {"tasks": tasks}, 2, 31)
        self.assertEqual(len(trials), 64)
        self.assertEqual(len({row["trial_id"] for row in trials}), 64)
        counts = {}
        for r in trials:
            key = (r["environment_condition"], r["prompt_condition"])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(set(counts.values()), {16})


if __name__ == "__main__":
    unittest.main()
