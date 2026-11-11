import unittest
from types import SimpleNamespace

from prepare_plan_handoff_experiment import (
    build_initial_ledger, update_ledger, render_ledger, build_arm_message,
)


class PlanHandoffPromptTests(unittest.TestCase):
    def setUp(self):
        self.prepared={
            "state":{"A","B"},"prefix_name":"Prefix_Tool",
            "prefix_observation":"Observed prefix output",
        }
        self.action={
            "tool":"Common_Action",
            "tool_result":"Native output: <Item> (Type: C)",
        }
        self.tool=SimpleNamespace(output_type="C")

    def test_ledger_contains_only_checkpoint_and_observed_action_facts(self):
        ledger=build_initial_ledger(self.prepared,self.action,self.tool)
        self.assertEqual(len(ledger["confirmed"]),2)
        self.assertEqual(ledger["confirmed"][0]["source_action"],"PREFIX-ACTION:Prefix_Tool")
        self.assertEqual(ledger["confirmed"][1]["observation_id"],"OBS-001")
        self.assertEqual(ledger["invalidated"],[])
        rendered=render_ledger(ledger)
        self.assertIn("Observed prefix output",rendered)
        self.assertIn("Native output",rendered)
        self.assertIn("remain unknown",rendered)

    def test_successful_update_adds_exact_observation(self):
        ledger=build_initial_ledger(self.prepared,self.action,self.tool)
        updated=update_ledger(ledger,"002","Next_Tool","D","Exact result",True)
        self.assertEqual(len(updated["confirmed"]),3)
        self.assertEqual(updated["confirmed"][-1]["exact_observation"],"Exact result")
        self.assertEqual(updated["confirmed"][-1]["source_action"],"002:Next_Tool")
        self.assertEqual(updated["invalidated"],[])

    def test_failed_update_does_not_claim_output_type(self):
        ledger=build_initial_ledger(self.prepared,self.action,self.tool)
        updated=update_ledger(ledger,"002","Next_Tool","D","[ERROR]",False)
        self.assertEqual(len(updated["confirmed"]),2)
        self.assertIn("state effect is unknown",updated["unknown"][-1])

    def test_factorial_arm_matrix_is_exact(self):
        path=["New_A","New_B"]
        ledger=build_initial_ledger(self.prepared,self.action,self.tool)
        messages={arm:build_arm_message(arm,path,ledger) for arm in "ABCD"}
        self.assertIn("previously supplied plan",messages["A"])
        self.assertNotIn("superseded",messages["A"])
        self.assertIn("superseded",messages["B"])
        self.assertNotIn("Confirmed:",messages["A"])
        self.assertNotIn("Confirmed:",messages["B"])
        self.assertIn("Confirmed:",messages["C"])
        self.assertIn("superseded",messages["D"])
        self.assertIn("Confirmed:",messages["D"])
        self.assertNotIn("New_A",messages["A"])
        self.assertIn("New_A -> New_B",messages["B"])


if __name__=="__main__":
    unittest.main()
