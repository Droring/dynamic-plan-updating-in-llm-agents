import unittest
from types import SimpleNamespace

from run_full_trajectory_comparison import COHORT, POLICIES, make_messages, summarize


class FullTrajectoryComparisonTests(unittest.TestCase):
    def test_cohort_and_policies_frozen(self):
        self.assertEqual(len(COHORT), 5)
        self.assertEqual(len(POLICIES), 3)
        self.assertEqual(len(set(COHORT)), 5)

    def test_control_prompt_does_not_disclose_optimality(self):
        p = {
            "user_request":"Reach destination.",
            "incumbent_suffix":["old","finish"],
            "state":{"Start"},
            "prefix_name":None,
            "prefix_observation":"Ready",
            "goal_type":"Goal",
            "task":"travel",
        }
        from unittest.mock import patch
        with patch("run_full_trajectory_comparison.screen.native.make_official_system_prompt",return_value="native"):
            messages = make_messages(p,object(),"alternate")
        text = messages[1]["content"]
        self.assertIn("FIRST tool call must invoke alternate",text)
        self.assertIn("Existing remaining plan",text)
        self.assertNotIn("oracle",text.lower())
        self.assertNotIn("SWITCH",text)

    def test_summary_reports_goal_and_path_quality_separately(self):
        rows = [
            {"policy":"incumbent","reached_goal":True,"path_regret":2.0,"provider_tokens":100,"halt_reason":"goal_reached"},
            {"policy":"candidate_gate","reached_goal":False,"path_regret":None,"provider_tokens":100,"halt_reason":"native_tool_error"},
            {"policy":"graph_planner","reached_goal":True,"path_regret":0.0,"provider_tokens":100,"halt_reason":"goal_reached"},
        ]
        out = summarize(rows,3)
        self.assertEqual(out["per_policy"]["candidate_gate"]["goals_reached"],0)
        self.assertEqual(out["per_policy"]["graph_planner"]["exact_reference_paths"],1)
        self.assertEqual(out["per_policy"]["incumbent"]["mean_path_regret"],2.0)


if __name__=="__main__":
    unittest.main()
