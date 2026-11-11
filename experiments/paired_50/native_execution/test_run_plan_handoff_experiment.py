import unittest
from types import SimpleNamespace

from run_plan_handoff_experiment import current_value, summarize, append_jsonl, save_json_durable, load_resume_state
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

    def test_resume_accepts_only_a_durable_completed_prefix(self):
        import json
        import tempfile
        from pathlib import Path

        requests=[
            {"trial_id":"trial-1","payload_sha256":"hash-1"},
            {"trial_id":"trial-2","payload_sha256":"hash-2"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"responses.jsonl").write_text(
                json.dumps({"trial_id":"trial-1","payload_sha256":"hash-1"})+"\n",
                encoding="utf-8",
            )
            ledger={
                "status":"incomplete","active_trial_id":None,
                "completed_trial_ids":["trial-1"],
                "approved_total_token_cap":3443584,
                "prior_orphaned_attempt_reserve":1000000,
                "effective_new_run_token_cap":2443584,
                "provider_tokens_charged_this_run":1200,
                "reservation_units_requested_this_run":30000,
            }
            (root/"ledger.json").write_text(json.dumps(ledger),encoding="utf-8")
            records,charged,reserved=load_resume_state(root,requests,2443584,3443584,1000000)
            self.assertEqual(len(records),1)
            self.assertEqual(charged,1200)
            self.assertEqual(reserved,30000)

    def test_resume_refuses_an_uncertain_active_trial(self):
        import json
        import tempfile
        from pathlib import Path

        requests=[{"trial_id":"trial-1","payload_sha256":"hash-1"}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"responses.jsonl").write_text(
                json.dumps({"trial_id":"trial-1","payload_sha256":"hash-1"})+"\n",
                encoding="utf-8",
            )
            ledger={
                "status":"incomplete","active_trial_id":"trial-1",
                "completed_trial_ids":["trial-1"],
                "approved_total_token_cap":3443584,
                "prior_orphaned_attempt_reserve":1000000,
                "effective_new_run_token_cap":2443584,
                "provider_tokens_charged_this_run":1200,
                "reservation_units_requested_this_run":30000,
            }
            (root/"ledger.json").write_text(json.dumps(ledger),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"stopped inside a trial"):
                load_resume_state(root,requests,2443584,3443584,1000000)

    def test_summary_counts_unknown_provider_outcomes(self):
        rows=[]
        for q in TASKS:
            for env in ENVIRONMENTS:
                for arm in ARMS:
                    for rep in (1,2):
                        rows.append({
                            "query_id":q,"environment":env,"arm":arm,
                            "repetition":rep,"goal_reached":False,
                            "continuation_regret":None,"full_path_regret":None,
                            "provider_tokens":0,"model_calls":0,
                            "halt_reason":"api_error:timeout",
                            "provider_outcome_unknown":False,
                        })
        rows[0]["provider_outcome_unknown"]=True
        summary=summarize(rows,80,SimpleNamespace(charged=0,reserved=0,cap=2443584))
        self.assertEqual(summary["unknown_provider_outcomes"],1)

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
