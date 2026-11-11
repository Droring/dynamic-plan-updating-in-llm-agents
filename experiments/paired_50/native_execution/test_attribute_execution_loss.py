import unittest
from types import SimpleNamespace

from attribute_execution_loss import attribute_one, TOL


class ExecutionLossAuditTests(unittest.TestCase):
    def setUp(self):
        def tool(inputs, output, value):
            return SimpleNamespace(input_types=set(inputs), output_type=output, cost=value)
        self.prepared = {
            "state":{"Start"}, "goal_type":"Goal", "checkpoint_sha256":"frozen",
            "tool_objects":{
                "a":tool(["Start"],"Mid",1.0),
                "b":tool(["Mid"],"Goal",1.0),
                "d":tool(["Mid"],"Extra",1.0),
                "direct":tool(["Start"],"Goal",2.0),
            }
        }

    def record(self, path, regret):
        return {
            "query_id":"Query00178","environment":"SWITCH",
            "policy":"graph_planner","checkpoint_sha256":"frozen",
            "reached_goal":True,"reference_value":2.0,
            "path_regret":regret,"path":path,
            "steps":[{"tool":name,"cost":self.prepared["tool_objects"][name].cost,
                      "output":"native observation", "success":True}
                     for name in path],
        }

    def test_loss_can_start_after_a_zero_loss_first_action(self):
        result=attribute_one(self.record(["a","d","b"],1.0),self.prepared)
        self.assertLessEqual(result["first_action_loss"],TOL)
        self.assertEqual(result["first_positive_loss_step"],2)
        self.assertEqual(result["later_action_loss"],1.0)
        self.assertEqual(result["recorded_path_regret"],result["total_bellman_loss"])

    def test_alternative_optimal_path_never_counted_as_error(self):
        result=attribute_one(self.record(["a","b"],0.0),self.prepared)
        self.assertIsNone(result["first_positive_loss_step"])
        self.assertEqual(result["total_bellman_loss"],0.0)

    def test_fail_closed_on_invalid_native_trace(self):
        broken=self.record(["a","b"],0.0)
        broken["steps"][1]["success"]=False
        with self.assertRaises(ValueError):
            attribute_one(broken,self.prepared)

    def test_fail_closed_on_inconsistent_telescoping(self):
        with self.assertRaises(ValueError):
            attribute_one(self.record(["a","d","b"],0.5),self.prepared)


if __name__ == "__main__":
    unittest.main()
