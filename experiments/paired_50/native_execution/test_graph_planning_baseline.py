import unittest
from types import SimpleNamespace

from graph_planning_baseline import shortest_feasible_path


class GraphPlannerTests(unittest.TestCase):
    def setUp(self):
        self.prepared = {
            "state": {"Start"}, "goal_type": "Goal",
            "tool_objects": {
                "old": SimpleNamespace(input_types={"Start"}, output_type="Goal", cost=10.0),
                "alternate": SimpleNamespace(input_types={"Start"}, output_type="Mid", cost=1.0),
                "finish": SimpleNamespace(input_types={"Mid"}, output_type="Goal", cost=1.0),
                "blocked": SimpleNamespace(input_types={"Unknown"}, output_type="Goal", cost=0.0),
            },
        }

    def test_shortest_path_compares_all_possible_first_tools(self):
        self.assertEqual(shortest_feasible_path(self.prepared), (2.0, ["alternate","finish"]))

    def test_horizon_one_picks_complete_old_action(self):
        self.assertEqual(shortest_feasible_path(self.prepared, max_steps=1), (10.0, ["old"]))

    def test_horizon_two_finds_better_route(self):
        self.assertEqual(shortest_feasible_path(self.prepared, max_steps=2), (2.0, ["alternate","finish"]))

    def test_initial_goal(self):
        p = dict(self.prepared, state={"Start","Goal"})
        self.assertEqual(shortest_feasible_path(p), (0.0, []))

    def test_negative_weight_rejected(self):
        self.prepared["tool_objects"]["old"].cost = -1
        with self.assertRaises(ValueError):
            shortest_feasible_path(self.prepared)


if __name__ == "__main__":
    unittest.main()
