from __future__ import annotations

import unittest

from .dry_run import interface
from .policy_input import build_policy_input
from .local_plan_substitution import generate_local_substitutions
from .submitted_plan_checker import check_policy_path


def make_policy(tool_interfaces, old_plan):
    return build_policy_input(
        task="local-substitution",
        user_request="Complete the typed workflow.",
        goal_type="Goal",
        observed_state_types=["Start"],
        old_remaining_plan=old_plan,
        current_tool_interfaces=tool_interfaces,
        checkpoint_id="local-substitution-checkpoint",
    )


class LocalPlanSubstitutionTests(unittest.TestCase):
    def test_single_tool_replaces_a_three_tool_suffix(self):
        tools = [
            interface("Search_Raw", ["Start"], "Raw", 2.0),
            interface("Refine_Raw", ["Raw"], "L1", 2.0),
            interface("Finish_L1", ["L1"], "Goal", 2.0),
            interface("Finish_Raw", ["Raw"], "Goal", 3.0),
        ]
        base = ["Search_Raw", "Refine_Raw", "Finish_L1"]
        policy = make_policy(tools, base)
        generated = generate_local_substitutions(policy, [base])
        self.assertTrue(generated)
        best = generated[0]
        self.assertEqual(best.candidate_path, ("Search_Raw", "Finish_Raw"))
        self.assertIn(("Finish_Raw",), [item.replacement_path for item in generated])
        self.assertEqual(best.source_value, 6.0)
        self.assertEqual(best.candidate_value, 5.0)
        self.assertTrue(check_policy_path(policy, best.candidate_path).valid)

    def test_two_tool_replacement_can_preserve_a_later_boundary_type(self):
        tools = [
            interface("Search_Raw", ["Start"], "Raw", 2.0),
            interface("Refine_Raw", ["Raw"], "L1", 2.0),
            interface("Finish_L1", ["L1"], "Goal", 2.0),
            interface("Search_to_L1", ["Start"], "L1", 3.0),
        ]
        base = ["Search_Raw", "Refine_Raw", "Finish_L1"]
        policy = make_policy(tools, base)
        generated = generate_local_substitutions(
            policy, [base], max_segment_length=4, max_replacement_length=2
        )
        self.assertIn(("Search_to_L1", "Finish_L1"),
                      [item.candidate_path for item in generated])
        self.assertEqual(generated[0].candidate_path,
                         ("Search_to_L1", "Finish_L1"))
        self.assertEqual(generated[0].candidate_value, 5.0)

    def test_full_path_validation_rejects_replacement_missing_suffix_input(self):
        tools = [
            interface("Search_Raw", ["Start"], "Raw", 1.0),
            interface("Refine_Raw", ["Raw"], "L1", 1.0),
            interface("Select_L1", ["L1"], "Selected", 1.0),
            interface("Finalize", ["L1", "Selected"], "Goal", 1.0),
            interface("Finish_Raw", ["Raw"], "Selected", 0.5),
        ]
        base = ["Search_Raw", "Refine_Raw", "Select_L1", "Finalize"]
        policy = make_policy(tools, base)
        generated = generate_local_substitutions(policy, [base])
        self.assertNotIn(
            ("Search_Raw", "Finish_Raw", "Finalize"),
            [item.candidate_path for item in generated],
        )
        self.assertTrue(check_policy_path(policy, base).valid)

    def test_equal_value_replacement_is_not_emitted(self):
        tools = [
            interface("Search_Raw", ["Start"], "Raw", 1.0),
            interface("Refine_Raw", ["Raw"], "L1", 1.0),
            interface("Finish_L1", ["L1"], "Goal", 1.0),
            interface("Finish_Raw", ["Raw"], "Goal", 2.0),
        ]
        base = ["Search_Raw", "Refine_Raw", "Finish_L1"]
        policy = make_policy(tools, base)
        generated = generate_local_substitutions(policy, [base])
        self.assertEqual(generated, ())

    def test_two_tool_replacement_respects_fixed_depth_bound(self):
        tools = [
            interface("Search_Raw", ["Start"], "Raw", 2.0),
            interface("Refine_Raw", ["Raw"], "L1", 2.0),
            interface("Finish_L1", ["L1"], "Goal", 2.0),
            interface("Prepare", ["Start"], "Seed", 1.0),
            interface("Search_from_Seed", ["Seed"], "L1", 1.0),
        ]
        base = ["Search_Raw", "Refine_Raw", "Finish_L1"]
        policy = make_policy(tools, base)
        one_step = generate_local_substitutions(
            policy, [base], max_segment_length=4, max_replacement_length=1
        )
        two_step = generate_local_substitutions(
            policy, [base], max_segment_length=4, max_replacement_length=2
        )
        self.assertNotIn(("Prepare", "Search_from_Seed", "Finish_L1"),
                         [item.candidate_path for item in one_step])
        self.assertIn(("Prepare", "Search_from_Seed", "Finish_L1"),
                      [item.candidate_path for item in two_step])

    def test_invalid_base_paths_are_not_used_as_anchors(self):
        tools = [interface("Finish", ["Missing"], "Goal", 1.0)]
        policy = make_policy(tools, ["Finish"])
        self.assertEqual(generate_local_substitutions(policy, [["Finish"]]), ())


if __name__ == "__main__":
    unittest.main()
