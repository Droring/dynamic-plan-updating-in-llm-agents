"""Full provider-free trajectory through the pinned native CostBench tools."""
from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from .run_complete_candidate import load_native_trial, run_native_offline_smoke


@unittest.skipUnless(
    os.environ.get("COSTBENCH_ROOT"),
    "COSTBENCH_ROOT is required for pinned native integration",
)
class PinnedCostBenchNativeTests(unittest.TestCase):
    def test_complete_committed_path_runs_to_goal_with_zero_provider_calls(self):
        root = Path(os.environ["COSTBENCH_ROOT"]).resolve()
        native, costbench, prepared, query = load_native_trial(
            root, query_id=None, condition="RETAIN", minimum_plan_length=2
        )
        result = asyncio.run(
            run_native_offline_smoke(prepared, query, native, costbench)
        )

        self.assertEqual(result.status, "goal_reached", msg=result.error)
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.decision.action, "RETAIN")
        self.assertEqual(result.decision.selected_plan, tuple(prepared["incumbent_suffix"]))
        self.assertEqual(result.executed_path, tuple(prepared["incumbent_suffix"]))
        self.assertEqual(result.planning_calls, 1)
        self.assertEqual(result.parameter_calls, len(result.executed_path))
        self.assertEqual(result.planning_tokens, 0)
        self.assertEqual(result.parameter_tokens, 0)
        self.assertGreaterEqual(len(result.trace), 2)
        self.assertEqual(len(result.trace), len(prepared["incumbent_suffix"]))
        self.assertTrue(all(row["success"] for row in result.trace))
        self.assertTrue(all(row["output_id"] for row in result.trace))

    def test_bounded_local_substitution_recovers_a_shorter_native_switch_path(self):
        root = Path(os.environ["COSTBENCH_ROOT"]).resolve()
        native, costbench, prepared, query = load_native_trial(
            root, query_id="Query00178", condition="SWITCH", minimum_plan_length=1
        )
        result = asyncio.run(
            run_native_offline_smoke(
                prepared, query, native, costbench,
                candidate_strategy="fresh_with_local_substitution",
            )
        )
        self.assertEqual(result.status, "goal_reached", msg=result.error)
        self.assertEqual(result.decision.action, "SWITCH")
        self.assertEqual(
            result.decision.selected_plan,
            ("Search_Transportation_Candidates", "Transportation_Finish_from_Step1_3Steps"),
        )
        self.assertEqual(result.executed_path, result.decision.selected_plan)
        self.assertEqual(result.planning_calls, 1)
        self.assertEqual(result.parameter_calls, 2)
        self.assertTrue(result.goal_reached)



if __name__ == "__main__":
    unittest.main()
