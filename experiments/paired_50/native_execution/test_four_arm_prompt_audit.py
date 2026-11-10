import unittest

from four_arm_prompt_audit import build_user_messages, validate_message_arms


class FourArmPromptTests(unittest.TestCase):
    def setUp(self):
        self.prepared = {
            "user_request": "Complete the task.",
            "incumbent_suffix": ["Old_Tool", "Finish_Tool"],
            "state": {"A", "B"},
            "prefix_name": "Prefix_Tool",
            "prefix_observation": "Prefix done.",
            "goal_type": "Goal",
        }

    def test_factorial_structure(self):
        messages = build_user_messages(self.prepared, "Alternative_Tool", 12.34)
        result = validate_message_arms(messages, "Alternative_Tool", 12.34)
        self.assertEqual(result["plan_visible"], {"A": True, "B": True, "C": False, "D": False})
        self.assertEqual(result["fact_localized"], {"A": False, "B": True, "C": False, "D": True})

    def test_non_plan_context_is_preserved(self):
        messages = build_user_messages(self.prepared, "Alternative_Tool", 12.34)
        for text in ("Complete the task.", "Prefix_Tool", "Prefix done.", "Current available data types: A, B", "Goal"):
            self.assertTrue(all(text in value for value in messages.values()), text)

    def test_only_b_and_d_localize_fact(self):
        messages = build_user_messages(self.prepared, "Alternative_Tool", 12.34)
        fact = "Current cost of Alternative_Tool: 12.34."
        self.assertNotIn(fact, messages["A"])
        self.assertIn(fact, messages["B"])
        self.assertNotIn(fact, messages["C"])
        self.assertIn(fact, messages["D"])

    def test_no_plan_arms_remove_only_plan_reference(self):
        messages = build_user_messages(self.prepared, "Alternative_Tool", 12.34)
        self.assertNotIn("Existing remaining plan", messages["C"])
        self.assertNotIn("existing plan", messages["C"])
        self.assertNotIn("Existing remaining plan", messages["D"])
        self.assertNotIn("existing plan", messages["D"])

    def test_shared_instruction_is_identical_across_all_arms(self):
        messages = build_user_messages(self.prepared, "Alternative_Tool", 12.34)
        common_tail = "Choose a feasible continuation from the current checkpoint. "
        for arm in "ABCD":
            self.assertEqual(messages[arm].count(common_tail), 1)
            self.assertIn("The tool environment has now changed.", messages[arm])
        plan_line = "Existing remaining plan, selected before the environment update: " + " -> ".join(self.prepared["incumbent_suffix"]) + "\n"
        self.assertEqual(messages["A"].replace(plan_line, ""), messages["C"])
        self.assertEqual(messages["B"].replace(plan_line, ""), messages["D"])


if __name__ == "__main__":
    unittest.main()
