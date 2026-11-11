import unittest
from types import SimpleNamespace

from run_plan_handoff_experiment import current_value, summarize
from preflight_common_action_restoration import TASKS, ENVIRONMENTS, ARMS


class PlanHandoffRunnerTests(unittest.TestCase):
    def test_current_value_uses_reconstructed_typed_state(self):
        tool=SimpleNamespace(input_types={"A"},output_type="Goal",cost=2.5)
        prepared={"state":{"A"},"goal_type":"Goal","tool_objects":{"finish":tool}}
        self.assertEqual(current_value(prepared,{"A"}),2.5)
        self.assertEqual(current_value(prepared,{"A","Goal"}),0.0)

    def test_summary_keeps_base_task_as_statistical_unit(self):
        rows=[]
        for q in TASKS:
            for env in ENVIRONMENTS:
                for arm in ARMS:
                    for rep in (1,2):
                        rows.append({
                            "query_id":q,"environment":env,"arm":arm,
                            "repetition":rep,"goal_reached":True,
                            "continuation_regret":0.25,"full_path_regret":0.5,
                            "provider_tokens":100,"model_calls":1,
                            "halt_reason":"goal_reached",
                        })
        summary=summarize(rows,80,SimpleNamespace(charged=8000,reserved=12000,cap=3443584))
        self.assertEqual(summary["completed_trajectories"],80)
        self.assertEqual(summary["independent_statistical_unit"],"base task (n=5)")
        self.assertEqual(summary["by_environment_and_arm"]["RETAIN/A"]["n"],10)
        self.assertEqual(summary["by_environment_and_arm"]["SWITCH/D"]["goals_reached"],10)


if __name__=="__main__":
    unittest.main()
