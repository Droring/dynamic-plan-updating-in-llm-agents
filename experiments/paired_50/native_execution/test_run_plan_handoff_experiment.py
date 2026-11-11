import unittest
from types import SimpleNamespace

from run_plan_handoff_experiment import current_value, summarize, append_jsonl, save_json_durable
from preflight_common_action_restoration import TASKS, ENVIRONMENTS, ARMS


class PlanHandoffRunnerTests(unittest.TestCase):
    def test_current_value_uses_reconstructed_typed_state(self):
        tool=SimpleNamespace(input_types={"A"},output_type="Goal",cost=2.5)
        prepared={"state":{"A"},"goal_type":"Goal","tool_objects":{"finish":tool}}
        self.assertEqual(current_value(prepared,{"A"}),2.5)
        self.assertEqual(current_value(prepared,{"A","Goal"}),0.0)

    def test_branch_clone_owns_independent_native_tool_objects_and_state(self):
        from run_plan_handoff_experiment import clone_trial_for_branch
        tool=SimpleNamespace(input_types={"A"},output_type="B",cost=1.0)
        trial={"prepared":{"tool_objects":{"step":tool},"state":{"A"}}}
        cloned=clone_trial_for_branch(trial)
        self.assertIsNot(cloned["prepared"]["tool_objects"],trial["prepared"]["tool_objects"])
        self.assertIsNot(cloned["prepared"]["tool_objects"]["step"],tool)
        self.assertIsNot(cloned["prepared"]["state"],trial["prepared"]["state"])

    def test_jsonl_append_is_durable_and_preserves_record_order(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"nested"/"responses.jsonl"
            append_jsonl(path,{"trial_id":"trial-1","provider_tokens":12})
            append_jsonl(path,{"trial_id":"trial-2","provider_tokens":18})
            rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["trial_id"] for row in rows],["trial-1","trial-2"])
            self.assertEqual(sum(row["provider_tokens"] for row in rows),30)

    def test_json_checkpoint_is_atomically_written(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"ledger.json"
            save_json_durable(path,{"status":"in_progress","charged":42})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["charged"],42)
            self.assertFalse(path.with_name(path.name+".tmp").exists())

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
