import unittest
from types import SimpleNamespace

from bounded_candidate_verifier import (
    candidate_completion, incumbent_path_value, verify,
)


class BoundedCandidateVerifierTests(unittest.TestCase):
    def setUp(self):
        self.prepared = {
            "state": {"Start"}, "goal_type": "Goal",
            "incumbent_suffix": ["old"],
            "tool_objects": {
                "old": SimpleNamespace(
                    input_types={"Start"}, output_type="Goal", cost=4.0),
                "alternate": SimpleNamespace(
                    input_types={"Start"}, output_type="Middle", cost=1.0),
                "finish": SimpleNamespace(
                    input_types={"Middle"}, output_type="Goal", cost=1.0),
                "expensive": SimpleNamespace(
                    input_types={"Start"}, output_type="Goal", cost=8.0),
                "blocked": SimpleNamespace(
                    input_types={"Missing"}, output_type="Goal", cost=0.0),
            },
        }

    def test_verifies_strictly_better_complete_candidate_path(self):
        result = verify(self.prepared, "old", "alternate")
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["certified_candidate_path"], ["alternate", "finish"])
        self.assertEqual(result["candidate_path_value"], 2.0)

    def test_retains_without_better_path(self):
        result = verify(self.prepared, "old", "expensive")
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["candidate_path_value"], 8.0)

    def test_no_oracle_required_to_reject_blocked_path(self):
        self.assertIsNone(candidate_completion(self.prepared, "blocked"))
        self.assertEqual(verify(self.prepared, "old", "blocked")["decision"], "KEEP")

    def test_horizon_limit_makes_uncertain_cases_retain(self):
        self.assertIsNone(candidate_completion(self.prepared, "alternate", max_steps=1))
        self.assertEqual(incumbent_path_value(self.prepared, ["old"]), 4.0)

    def test_equal_value_does_not_trigger_switch(self):
        self.prepared["tool_objects"]["finish"].cost = 3.0
        self.assertEqual(verify(self.prepared, "old", "alternate")["decision"], "KEEP")

    def test_validates_existing_suffix(self):
        self.assertIsNone(incumbent_path_value(self.prepared, ["blocked"]))
        with self.assertRaises(ValueError):
            verify(self.prepared, "alternate", "old")


if __name__ == "__main__":
    unittest.main()
