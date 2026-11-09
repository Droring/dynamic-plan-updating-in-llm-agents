import unittest

from native_path_value_audit import TOL, replay, value


class NativePathValueAuditTests(unittest.TestCase):
    def setUp(self):
        self.tools = {
            "A": {"input_types": [], "output_type": "X", "cost": 1.0},
            "B": {"input_types": ["X"], "output_type": "G", "cost": 1.0},
            "C": {"input_types": [], "output_type": "G", "cost": 3.0},
        }

    def test_dijkstra_finds_minimum_type_feasible_value(self):
        optimum, path = value(self.tools, set(), "G")
        self.assertAlmostEqual(optimum, 2.0)
        self.assertEqual(path, ["A", "B"])

    def test_replay_validates_native_trace_and_goal(self):
        trace = [
            {"tool_name": "A", "tool_cost": 1.0, "success": True},
            {"tool_name": "B", "tool_cost": 1.0, "success": True},
        ]
        total = replay(["A", "B"], self.tools, set(), "G", trace=trace)
        self.assertAlmostEqual(total, 2.0)

    def test_replay_rejects_cost_mismatch(self):
        trace = [{"tool_name": "A", "tool_cost": 1.1, "success": True}]
        with self.assertRaises(ValueError):
            replay(["A"], self.tools, set(), "G", trace=trace)

    def test_replay_rejects_infeasible_tool_order(self):
        with self.assertRaises(ValueError):
            replay(["B", "A"], self.tools, set(), "G")

    def test_optimality_regret_is_value_not_path_identity(self):
        optimum, _ = value(self.tools, set(), "G")
        alternative_cost = replay(["C"], self.tools, set(), "G")
        self.assertAlmostEqual(alternative_cost - optimum, 1.0)
        equal_value_cost = replay(["A", "B"], self.tools, set(), "G")
        self.assertLessEqual(abs(equal_value_cost - optimum), TOL)


if __name__ == "__main__":
    unittest.main()
