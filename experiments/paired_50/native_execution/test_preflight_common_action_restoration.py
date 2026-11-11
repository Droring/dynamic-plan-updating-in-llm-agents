import unittest

from preflight_common_action_restoration import (
    TASKS, ENVIRONMENTS, POLICIES, ARMS,
    select_common_actions, validate_branch_records,
)


def archive_fixture():
    rows=[]
    for q in TASKS:
        for env in ENVIRONMENTS:
            for policy in ("incumbent","candidate_gate","graph_planner"):
                tool=f"{q}_shared_action"
                args='{"x": 1}'
                output=f"native result {q} {env} {policy}"
                rows.append({
                    "query_id":q,"environment":env,"policy":policy,
                    "source_trial_id":f"{q}_{env}_{policy}_source",
                    "checkpoint_sha256":f"checkpoint-{q}",
                    "reached_goal":True,"controlled_first_action":tool,
                    "path":[tool,"terminal_action"],
                    "steps":[{"tool":tool,"arguments":args,"output":output,
                              "cost":1.0,"success":True},
                             {"tool":"terminal_action","arguments":"{}",
                              "output":"goal","cost":1.0,"success":True}],
                })
    return rows


def branch_fixture(actions):
    outputs={}
    for arm_index,arm in enumerate(ARMS):
        rows=[]
        for action in actions:
            result=action["expected_archived_tool_result"]
            if result is None:
                result=f"native result {action['query_id']} {action['environment']} {action['source_policy']}"
            import hashlib
            result_sha=hashlib.sha256(result.encode()).hexdigest()
            rows.append({
                "query_id":action["query_id"],"environment":action["environment"],
                "paired_source_trial_id":action["paired_source_trial_id"],
                "source_action_trial_id":action["source_action_trial_id"],
                "source_environment":action["source_environment"],
                "source_policy":action["source_policy"],
                "checkpoint_sha256":action["checkpoint_sha256"],
                "tool":action["tool"],"arguments":action["arguments"],
                "arguments_sha256":action["arguments_sha256"],
                "tool_result":result,"tool_result_sha256":result_sha,
                "native_success":True,"recorded_cost":1.0,
                "output_type":"Intermediate",
                "initial_state_sha256":"initial",
                "post_action_state_sha256":"post",
                "tool_registry_sha256":"registry",
                "process_id":100+arm_index,
            })
        outputs[arm]={"arm":arm,"status":"worker_complete","rows":rows}
    return outputs


class CommonActionRestorationTests(unittest.TestCase):
    def test_selects_shared_nonterminal_action_for_both_environment_conditions(self):
        actions=select_common_actions(archive_fixture())
        self.assertEqual(len(actions),10)
        for q in TASKS:
            pair=[x for x in actions if x["query_id"]==q]
            self.assertEqual(len(pair),2)
            self.assertEqual(pair[0]["tool"],pair[1]["tool"])
            self.assertEqual(pair[0]["arguments"],pair[1]["arguments"])

    def test_rejects_missing_or_duplicate_trajectory(self):
        rows=archive_fixture()
        with self.assertRaises(ValueError):
            select_common_actions(rows[:-1])
        with self.assertRaises(ValueError):
            select_common_actions(rows+[rows[0]])

    def test_requires_four_independent_restorations_and_matches_source_archive(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        report=validate_branch_records(actions,outputs)
        self.assertEqual(len(report),10)
        self.assertTrue(all(x["native_result_match_across_arms"] for x in report))

    def test_rejects_native_result_mismatch(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        source_action=next(x for x in actions if x["environment"]==x["source_environment"])
        target=outputs["D"]["rows"]
        row=next(x for x in target if x["query_id"]==source_action["query_id"] and x["environment"]==source_action["environment"])
        row["tool_result"]="different"
        with self.assertRaises(ValueError):
            validate_branch_records(actions,outputs)

    def test_rejects_reused_process(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        for row in outputs["D"]["rows"]:
            row["process_id"]=outputs["C"]["rows"][0]["process_id"]
        with self.assertRaises(ValueError):
            validate_branch_records(actions,outputs)


if __name__=="__main__":
    unittest.main()
