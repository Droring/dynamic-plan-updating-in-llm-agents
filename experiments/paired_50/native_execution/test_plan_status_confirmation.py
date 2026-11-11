import unittest
from types import SimpleNamespace

import prepare_plan_status_confirmation as study


class PlanStatusConfirmationTests(unittest.TestCase):
    def test_path_value_uses_supplied_post_action_state(self):
        prepared = {
            "goal_type": "Goal",
            "tool_objects": {
                "finish": SimpleNamespace(input_types=["Intermediate"], output_type="Goal", cost=3.5),
                "wrong": SimpleNamespace(input_types=["Missing"], output_type="Goal", cost=1.0),
            },
        }
        self.assertEqual(study.path_value(prepared, {"Start", "Intermediate"}, ["finish"]), 3.5)
        self.assertIsNone(study.path_value(prepared, {"Start"}, ["finish"]))
        self.assertIsNone(study.path_value(prepared, {"Start", "Intermediate"}, ["wrong"]))

    def test_prior_status_treats_ties_as_valid(self):
        self.assertEqual(study.classify_prior_status(10.0, 10.0), ("VALID", 0.0))
        self.assertEqual(study.classify_prior_status(10.0000001, 10.0)[0], "VALID")
        self.assertEqual(study.classify_prior_status(12.5, 10.0), ("STALE", 2.5))
        with self.assertRaises(ValueError):
            study.classify_prior_status(9.0, 10.0)

    def test_prompt_has_one_status_label_difference(self):
        common = ("ToolA", ["ToolB", "ToolC"], ["ToolD"], "Goal")
        unmarked = study.make_status_message(*common, "UNSET")
        annotated = study.make_status_message(*common, "STALE")
        self.assertEqual(
            unmarked.replace("Prior-plan status: UNSET.", "<STATUS>"),
            annotated.replace("Prior-plan status: STALE.", "<STATUS>"),
        )
        valid = study.make_status_message(*common, "VALID")
        self.assertTrue(valid.endswith("Prior-plan status: VALID."))

    def test_selection_is_lexicographic_and_category_balanced(self):
        categories = ("transportation", "accommodation", "attraction", "dining", "shopping")
        candidates = [
            {"query_id": f"Query{i:05d}", "category": category, "cells": {}}
            for category in categories
            for i in (9, 2, 5)
        ]
        selected = study.select_tasks(candidates)
        self.assertEqual(len(selected), 10)
        for category in categories:
            ids = [x["query_id"] for x in selected if x["category"] == category]
            self.assertEqual(ids, sorted(ids)[:2])


if __name__ == "__main__":
    unittest.main()
