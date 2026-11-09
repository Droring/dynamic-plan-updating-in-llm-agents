import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from run_official_harness import (
    DATA_DIR,
    TokenBudget,
    audit_prepared_pairs,
    classify_first_action,
    grade_execution,
    load_frozen_inputs,
    load_resume_checkpoint,
    make_checkpoint_user_message,
    relevant_tool_names,
    restore_partial_execution,
    trajectory_relation,
    walk_type_state,
)


class FrozenDatasetTests(unittest.TestCase):
    def test_frozen_dataset_has_fifty_pairs_and_balanced_conditions(self):
        requests, manifest, registry = load_frozen_inputs(DATA_DIR)
        self.assertEqual(len(requests), 100)
        self.assertEqual(len(manifest), 100)
        self.assertEqual(registry["base_task_count"], 50)
        self.assertEqual(
            Counter(row["condition"] for row in manifest.values()),
            {"RETAIN": 50, "SWITCH": 50},
        )

    def test_each_task_has_exactly_two_conditions(self):
        requests, manifest, _ = load_frozen_inputs(DATA_DIR)
        grouped = {}
        for request in requests:
            grouped.setdefault(request["query_id"], []).append(
                manifest[request["trial_id"]]["condition"]
            )
        self.assertEqual(len(grouped), 50)
        for conditions in grouped.values():
            self.assertCountEqual(conditions, ["RETAIN", "SWITCH"])


class TypeGraphTests(unittest.TestCase):
    def test_relevant_tool_filter_keeps_goal_paths_only(self):
        tools = {
            "make_a": {"input_types": ["S"], "output_type": "A"},
            "make_goal": {"input_types": ["A"], "output_type": "G"},
            "irrelevant": {"input_types": ["X"], "output_type": "Y"},
        }
        self.assertEqual(
            relevant_tool_names(tools, {"S"}, "G"),
            {"make_a", "make_goal"},
        )

    def test_type_state_walk_accepts_feasible_path(self):
        tools = {
            "first": {"input_types": ["S"], "output_type": "A"},
            "second": {"input_types": ["A"], "output_type": "G"},
        }
        self.assertEqual(walk_type_state({"S"}, ["first", "second"], tools), {"S", "A", "G"})

    def test_type_state_walk_rejects_missing_precondition(self):
        tools = {
            "second": {"input_types": ["A"], "output_type": "G"},
        }
        with self.assertRaisesRegex(ValueError, "not type-feasible"):
            walk_type_state({"S"}, ["second"], tools)


class ResumeTests(unittest.TestCase):
    def test_restore_partial_trace_rebuilds_tool_context_without_reexecuting_tools(self):
        prepared = {
            "state": {"S"},
            "tool_objects": {
                "make_a": SimpleNamespace(input_types={"S"}, output_type="A"),
            },
        }
        record = {
            "trace": [{
                "tool_name": "make_a",
                "arguments": '{"source":"S1"}',
                "output": "A1 created",
                "success": True,
            }],
            "executed_path": ["make_a"],
            "final_state_types": ["A", "S"],
            "first_action": "make_a",
        }
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ]
        state, path, trace = restore_partial_execution(prepared, record, messages)
        self.assertEqual(state, {"S", "A"})
        self.assertEqual(path, ["make_a"])
        self.assertEqual(len(trace), 1)
        self.assertEqual([message["role"] for message in messages], [
            "system", "user", "assistant", "tool"
        ])
        self.assertEqual(messages[-1]["content"], "A1 created")
        self.assertEqual(messages[-2]["tool_calls"][0]["function"]["name"], "make_a")

    def test_restore_partial_trace_rejects_state_inconsistent_replay(self):
        prepared = {
            "state": {"S"},
            "tool_objects": {
                "make_a": SimpleNamespace(input_types={"X"}, output_type="A"),
            },
        }
        record = {
            "trace": [{
                "tool_name": "make_a",
                "arguments": "{}",
                "output": "A1",
                "success": True,
            }],
            "executed_path": ["make_a"],
            "final_state_types": ["A", "S"],
            "first_action": "make_a",
        }
        with self.assertRaisesRegex(ValueError, "not type-feasible"):
            restore_partial_execution(prepared, record, [])

    def test_resume_checkpoint_checks_hashes_order_and_token_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_dir = root / "generated"
            resume_dir = root / "partial"
            data_dir.mkdir()
            resume_dir.mkdir()
            requests = [
                {
                    "trial_id": f"trial-{index}",
                    "query_id": f"Query{index:05d}",
                    "checkpoint_sha256": f"checkpoint-{index}",
                }
                for index in range(100)
            ]
            manifest = {
                request["trial_id"]: {
                    "condition": "RETAIN" if index % 2 == 0 else "SWITCH",
                    "query_id": request["query_id"],
                    "checkpoint_sha256": request["checkpoint_sha256"],
                }
                for index, request in enumerate(requests)
            }
            (data_dir / "model_requests_100.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in requests), encoding="utf-8"
            )
            (data_dir / "trial_manifest_100.json").write_text(
                json.dumps({"records": [
                    {"trial_id": request["trial_id"], **manifest[request["trial_id"]]}
                    for request in requests
                ]}),
                encoding="utf-8",
            )
            first = {
                "trial_id": requests[0]["trial_id"],
                "request_sha256": hashlib.sha256(
                    json.dumps(requests[0], sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "checkpoint_sha256": requests[0]["checkpoint_sha256"],
                "condition": "RETAIN",
                "halt_reason": "goal_reached",
                "goal_state_reached": True,
                "provider_total_tokens": 10,
            }
            partial = {
                "trial_id": requests[1]["trial_id"],
                "request_sha256": hashlib.sha256(
                    json.dumps(requests[1], sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "checkpoint_sha256": requests[1]["checkpoint_sha256"],
                "condition": "SWITCH",
                "halt_reason": "reservation_cap",
                "goal_state_reached": False,
                "provider_total_tokens": 5,
                "model_calls": 1,
                "trace": [{"tool_name": "first"}],
            }
            (resume_dir / "responses.jsonl").write_text(
                json.dumps(first) + "\n" + json.dumps(partial) + "\n", encoding="utf-8"
            )
            input_sha = hashlib.sha256(
                (data_dir / "model_requests_100.jsonl").read_bytes()
            ).hexdigest()
            manifest_sha = hashlib.sha256(
                (data_dir / "trial_manifest_100.json").read_bytes()
            ).hexdigest()
            (resume_dir / "ledger.json").write_text(json.dumps({
                "status": "incomplete",
                "attempted_trials": 2,
                "planned_trials": 100,
                "charged_tokens": 15,
                "reserved_tokens": 200,
            }), encoding="utf-8")
            (resume_dir / "scores.json").write_text(json.dumps({
                "status": "incomplete",
                "accounted_tokens": 15,
                "input_sha256": input_sha,
                "manifest_sha256": manifest_sha,
            }), encoding="utf-8")

            result = load_resume_checkpoint(resume_dir, requests, manifest, data_dir)
            self.assertEqual(len(result["completed_records"]), 1)
            self.assertEqual(result["partial_record"]["trial_id"], "trial-1")
            self.assertEqual(result["resume_index"], 1)
            self.assertEqual(result["charged_tokens"], 15)
            self.assertEqual(result["reserved_tokens"], 200)

            partial["request_sha256"] = "tampered"
            (resume_dir / "responses.jsonl").write_text(
                json.dumps(first) + "\n" + json.dumps(partial) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "request hash mismatch"):
                load_resume_checkpoint(resume_dir, requests, manifest, data_dir)


class ActionScoringTests(unittest.TestCase):
    def test_token_budget_restores_cumulative_usage(self):
        budget = TokenBudget(1000, charged=600, reserved=2500)
        self.assertTrue(budget.can_call(400))
        self.assertFalse(budget.can_call(401))
        self.assertEqual(budget.charged, 600)
        self.assertEqual(budget.reserved, 2500)

    def test_first_action_classification(self):
        incumbent = ["old_first", "old_second"]
        self.assertEqual(classify_first_action(["old_first"], incumbent), "RETAIN")
        self.assertEqual(classify_first_action(["alternative"], incumbent), "SWITCH")
        self.assertIsNone(classify_first_action([], incumbent))

    def test_trajectory_relation_preserves_later_deviation(self):
        incumbent = ["a", "b", "c"]
        self.assertEqual(trajectory_relation(["a", "b", "c"], incumbent), "exact_incumbent_suffix")
        self.assertEqual(trajectory_relation(["a", "b"], incumbent), "incumbent_prefix")
        self.assertEqual(
            trajectory_relation(["a", "different"], incumbent),
            "started_incumbent_then_diverged",
        )
        self.assertEqual(trajectory_relation(["other"], incumbent), "alternative_continuation")

    def test_checkpoint_prompt_does_not_include_gold_condition(self):
        prepared = {
            "user_request": "Plan a trip.",
            "incumbent_suffix": ["tool_a", "tool_b"],
            "state": {"TimeInfo", "Candidate_Raw"},
            "prefix_name": "prefix_tool",
            "prefix_observation": "A candidate set is ready.",
            "goal_type": "TravelGoal",
        }
        message = make_checkpoint_user_message(prepared)
        self.assertIn("Existing remaining plan", message)
        self.assertIn("environment has now changed", message)
        self.assertNotIn("RETAIN", message)
        self.assertNotIn("SWITCH", message)

    def test_paired_audit_accepts_same_checkpoint_and_tools(self):
        rows = []
        for index in range(50):
            base = {
                "query_id": f"Query{index:05d}",
                "task": "transportation",
                "checkpoint_sha256": f"checkpoint-{index}",
                "prefix": ["prefix"],
                "incumbent_suffix": ["old"],
                "changed_tool": "changed",
                "tool_objects": {"old", "new"},
            }
            rows.extend([
                {**base, "condition": "RETAIN"},
                {**base, "condition": "SWITCH"},
            ])
        result = audit_prepared_pairs(rows)
        self.assertEqual(result["base_tasks"], 50)
        self.assertEqual(result["trials"], 100)
        self.assertEqual(result["category_counts"], {"transportation": 50})
        self.assertEqual(result["prefix_tool_count"], 50)

    def test_grade_execution_reports_incumbent_deviation_as_behavior(self):
        manifest = {
            "trial-retain": {
                "query_id": "Query00001",
                "condition": "RETAIN",
                "request_sha256": "hash-retain",
            },
            "trial-switch": {
                "query_id": "Query00001",
                "condition": "SWITCH",
                "request_sha256": "hash-switch",
            },
        }
        records = [
            {
                "trial_id": "trial-retain",
                "request_sha256": "hash-retain",
                "first_action_prediction": "RETAIN",
                "trajectory_relation": "exact_incumbent_suffix",
                "goal_state_reached": True,
                "provider_total_tokens": 100,
            },
            {
                "trial_id": "trial-switch",
                "request_sha256": "hash-switch",
                "first_action_prediction": "SWITCH",
                "trajectory_relation": "alternative_continuation",
                "goal_state_reached": True,
                "provider_total_tokens": 120,
            },
        ]
        result = grade_execution(records, manifest, planned_trials=2)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["cohort_complete"])
        self.assertEqual(result["cohort_coverage"], 0.02)
        self.assertEqual(result["paired_tasks_attempted"], 1)
        self.assertEqual(result["paired_first_action_behavior"], {"RETAIN/SWITCH": 1})
        self.assertEqual(result["first_action_followed_incumbent"], 1)
        self.assertEqual(result["first_action_departed_incumbent"], 1)
        self.assertEqual(result["goal_state_reached"], 2)
        self.assertEqual(result["provider_total_tokens"], 220)
        self.assertIn("Neither label alone establishes", result["interpretation"])

    def test_missing_first_action_is_reported_without_optimality_claim(self):
        manifest = {
            "trial-retain": {
                "query_id": "Query00001",
                "condition": "RETAIN",
                "request_sha256": "hash-retain",
            },
            "trial-switch": {
                "query_id": "Query00001",
                "condition": "SWITCH",
                "request_sha256": "hash-switch",
            },
        }
        records = [
            {
                "trial_id": "trial-retain",
                "request_sha256": "hash-retain",
                "first_action_prediction": None,
                "trajectory_relation": "no_tool_action",
                "goal_state_reached": False,
                "provider_total_tokens": 10,
            },
            {
                "trial_id": "trial-switch",
                "request_sha256": "hash-switch",
                "first_action_prediction": "SWITCH",
                "trajectory_relation": "alternative_continuation",
                "goal_state_reached": True,
                "provider_total_tokens": 20,
            },
        ]
        result = grade_execution(records, manifest, planned_trials=2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["paired_first_action_behavior"], {"None/SWITCH": 1})
        self.assertEqual(result["retain_condition_first_action_behavior"]["no_first_action"], 1)
        self.assertEqual(result["switch_condition_first_action_behavior"]["departed_incumbent"], 1)
        self.assertEqual(result["goal_state_reached"], 1)
        self.assertIn("not establish current-condition optimality", result["interpretation"])



if __name__ == "__main__":
    unittest.main()
