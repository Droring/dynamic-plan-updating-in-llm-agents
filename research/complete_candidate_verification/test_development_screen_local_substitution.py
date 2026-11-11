from __future__ import annotations

import base64
import json
import unittest
import zlib
from pathlib import Path

from .local_plan_substitution import generate_local_substitutions
from .policy_input import build_policy_input
from .submitted_plan_checker import check_policy_path, select_strictly_better_plan


FIXTURE_PATH = Path(__file__).with_name(
    "development_screen_local_substitution_fixture.zlib.b64"
)


def load_fixture():
    compressed = base64.b64decode(FIXTURE_PATH.read_text(encoding="ascii"))
    return json.loads(zlib.decompress(compressed).decode("utf-8"))


def make_interfaces(task, condition):
    interfaces = []
    for item in task["tools"]:
        cost_key = "retain_cost" if condition == "RETAIN" else "switch_cost"
        cost = item[cost_key]
        interfaces.append({
            "type": "function",
            "function": {
                "name": item["name"],
                "description": (
                    f"This tool has a cost of {cost:g} units. "
                    f"The output type of this tool is {item['output_type']}."
                ),
                "parameters": {
                    "properties": {name: {} for name in item["required_inputs"]},
                    "required": list(item["required_inputs"]),
                    "type": "object",
                },
            },
        })
    return interfaces


class DevelopmentScreenLocalSubstitutionAuditTests(unittest.TestCase):
    def test_all_sixteen_development_checkpoints_against_posthoc_optima(self):
        fixture = load_fixture()
        self.assertEqual(fixture["schema"],
                         "development-screen-local-substitution-retrospective-audit-v1")
        self.assertEqual(len(fixture["tasks"]), 8)
        retain_correct = 0
        switch_correct = 0
        fresh_already_optimal = 0
        local_operator_recovers_optimal = 0

        for task in fixture["tasks"]:
            for condition in ("RETAIN", "SWITCH"):
                with self.subTest(query=task["query_id"], condition=condition):
                    record = task["conditions"][condition]
                    interfaces = make_interfaces(task, condition)
                    policy_input = build_policy_input(
                        task=task["query_id"],
                        user_request="Complete the task using the current tool catalogue.",
                        goal_type=task["goal_type"],
                        observed_state_types=task["current_state_types"],
                        old_remaining_plan=record["incumbent_path"],
                        current_tool_interfaces=interfaces,
                        checkpoint_id=f"{task['query_id']}-frozen-checkpoint",
                    )
                    # Condition labels and oracle scores are scoring-only fixture fields.
                    self.assertFalse(hasattr(policy_input, "condition"))
                    self.assertFalse(hasattr(policy_input, "oracle_optimal_value"))
                    self.assertNotIn("condition", policy_input.prompt_payload(
                        include_incumbent=False))
                    self.assertNotIn("oracle_optimal_value", policy_input.prompt_payload(
                        include_incumbent=False))

                    fresh_path = tuple(record["fresh_path"])
                    fresh_check = check_policy_path(policy_input, fresh_path)
                    self.assertTrue(fresh_check.valid)
                    self.assertIsNotNone(fresh_check.cost)

                    substitutions = generate_local_substitutions(
                        policy_input,
                        [record["incumbent_path"], record["fresh_path"]],
                        max_segment_length=fixture["policy_configuration"]["max_segment_length"],
                        max_replacement_length=fixture["policy_configuration"]["max_replacement_length"],
                    )
                    candidate_paths = [fresh_path] + [
                        item.candidate_path for item in substitutions
                    ]
                    decision = select_strictly_better_plan(policy_input, candidate_paths)
                    self.assertIsNotNone(decision.selected_check)
                    self.assertEqual(
                        decision.selected_check.cost,
                        record["oracle_optimal_value"],
                    )

                    if condition == "RETAIN":
                        self.assertEqual(decision.action, "RETAIN")
                        self.assertEqual(
                            decision.selected_plan,
                            tuple(record["incumbent_path"]),
                        )
                        retain_correct += 1
                    else:
                        self.assertEqual(decision.action, "SWITCH")
                        self.assertLess(
                            decision.selected_check.cost,
                            record["incumbent_value"] - 1e-6,
                        )
                        switch_correct += 1
                        if fresh_check.cost == record["oracle_optimal_value"]:
                            fresh_already_optimal += 1
                        if any(item.candidate_value == record["oracle_optimal_value"]
                               for item in substitutions):
                            local_operator_recovers_optimal += 1

        self.assertEqual(retain_correct, 8)
        self.assertEqual(switch_correct, 8)
        self.assertEqual(fresh_already_optimal, 2)
        self.assertEqual(local_operator_recovers_optimal, 6)


if __name__ == "__main__":
    unittest.main()
