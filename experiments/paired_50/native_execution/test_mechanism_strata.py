import unittest

from analyze_mechanism_strata import TOL, classify_changed_tool


class MechanismStrataTests(unittest.TestCase):
    def test_incumbent_tool_increase(self):
        self.assertEqual(
            classify_changed_tool("A", ["A", "B"], 1.3),
            "incumbent_tool_increased",
        )

    def test_outside_alternative_decrease(self):
        self.assertEqual(
            classify_changed_tool("C", ["A", "B"], -1.3),
            "outside_alternative_decreased",
        )

    def test_other_change_is_not_misclassified(self):
        self.assertEqual(
            classify_changed_tool("A", ["A"], -0.2),
            "incumbent_tool_other_change",
        )
        self.assertEqual(
            classify_changed_tool("C", ["A"], 0.2),
            "outside_tool_other_change",
        )

    def test_tolerance_boundary(self):
        self.assertEqual(
            classify_changed_tool("C", ["A"], TOL / 2),
            "outside_tool_other_change",
        )


if __name__ == "__main__":
    unittest.main()
