import unittest

from preflight_common_action_restoration import (
    TASKS, ENVIRONMENTS, POLICIES, ARMS,
    select_common_actions, validate_branch_records,
)


def archive_fixture():
    rows=[]
    for q in TASKS:
        for env in ENVIRONMENTS:
            for policy in POLICIES:
                tool=f"{q}_{env}_{policy}"
                args='{"x": 1}'
                output=f"native result {q} {env} {policy}"
                rows.append({
                    "query_id":q,"environment":env,"policy":policy,
                    "source_trial_id":f"{q}_{env}_source",
                    "checkpoint_sha256":f"checkpoint-{q}",
                    "reached_goal":True,"controlled_first_action":tool,
                    "path":[tool],
                    "steps":[{"tool":tool,"arguments":args,"output":output,
                              "cost":1.0,"success":True}],
                })
    return rows


def branch_fixture(actions):
    outputs={}
    for arm_index,arm in enumerate(ARMS):
        rows=[]
        for action in actions:
            rows.append({
                "query_id":action["query_id"],"environment":action["environment"],
                "source_trial_id":action["source_trial_id"],
                "checkpoint_sha256":action["checkpoint_sha256"],
                "tool":action["tool"],"arguments":action["arguments"],
                "arguments_sha256":action["arguments_sha256"],
                "tool_result":action["tool_result"],
                "tool_result_sha256":action["tool_result_sha256"],
                "native_success":True,"recorded_cost":1.0,
                "output_type":"Output",
                "initial_state_sha256":"initial",
                "post_action_state_sha256":"post",
                "tool_registry_sha256":"registry",
                "process_id":100+arm_index,
            })
        outputs[arm]={"arm":arm,"status":"worker_complete","rows":rows}
    return outputs


class CommonActionRestorationTests(unittest.TestCase):
    def test_selects_exactly_ten_graph_planner_first_actions(self):
        actions=select_common_actions(archive_fixture())
        self.assertEqual(len(actions),10)
        self.assertTrue(all(a["tool"].endswith("_graph_planner") for a in actions))

    def test_rejects_missing_or_duplicate_trajectory(self):
        rows=archive_fixture()
        with self.assertRaises(ValueError):
            select_common_actions(rows[:-1])
        with self.assertRaises(ValueError):
            select_common_actions(rows+[rows[0]])

    def test_requires_exactly_four_independent_restorations(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        report=validate_branch_records(actions,outputs)
        self.assertEqual(len(report),10)
        self.assertTrue(all(x["exact_native_result_match"] for x in report))

    def test_rejects_native_result_mismatch(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        outputs["D"]["rows"][0]["tool_result"]="different"
        with self.assertRaises(ValueError):
            validate_branch_records(actions,outputs)

    def test_rejects_reused_process(self):
        actions=select_common_actions(archive_fixture())
        outputs=branch_fixture(actions)
        outputs["D"]["process_id"]=outputs["C"]["process_id"]
        for row in outputs["D"]["rows"]:
            row["process_id"]=outputs["C"]["process_id"]
        with self.assertRaises(ValueError):
            validate_branch_records(actions,outputs)


if __name__=="__main__":
    unittest.main()
