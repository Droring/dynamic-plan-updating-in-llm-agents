import unittest

from analyze_mechanism_strata import TOL, classify_changed_tool, locate_changed_tool


class MechanismStrataTests(unittest.TestCase):
    def test_incumbent_tool_increase(self):
        self.assertEqual(classify_changed_tool("A", ["A", "B"], 1.3), "incumbent_tool_increased")

    def test_outside_alternative_decrease(self):
        self.assertEqual(classify_changed_tool("C", ["A", "B"], -1.3), "outside_alternative_decreased")

    def test_other_change_is_not_misclassified(self):
        self.assertEqual(classify_changed_tool("A", ["A"], -0.2), "incumbent_tool_other_change")
        self.assertEqual(classify_changed_tool("C", ["A"], 0.2), "outside_tool_other_change")

    def test_tolerance_boundary(self):
        self.assertEqual(classify_changed_tool("C", ["A"], TOL / 2), "outside_tool_other_change")

    def test_changed_tool_position(self):
        self.assertEqual(locate_changed_tool("A", ["A", "B"]), ("first_incumbent_action", 1))
        self.assertEqual(locate_changed_tool("B", ["A", "B"]), ("later_incumbent_action", 2))
        self.assertEqual(locate_changed_tool("C", ["A", "B"]), ("outside_incumbent", 0))


if __name__ == "__main__":
    unittest.main()
