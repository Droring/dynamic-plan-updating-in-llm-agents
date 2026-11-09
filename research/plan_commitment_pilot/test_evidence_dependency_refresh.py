#!/usr/bin/env python3
import unittest
from evidence_dependency_refresh import build_ledger

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.history=[{"role":"assistant","tool_calls":[{"function":{"name":"Decide_Transportation_Preference","arguments":'{"TransportationStyle":"comfort_priority"}'}}]}]
        self.tools=[{"type":"function","function":{"name":"Decide_Transportation_Preference"}}]
    def test_update(self):
        x=build_ledger(self.history,"Current transportation style preference: scenic_route. Please complete the existing transportation request.",[],self.tools)
        self.assertEqual(x["status"],"changed")
        self.assertEqual(x["original_style"],"comfort_priority")
        self.assertEqual(x["new_style"],"scenic_route")
        self.assertIn("does not establish",x["intervention"])
    def test_retain(self):
        x=build_ledger(self.history,"Current transportation style preference: comfort_priority. Please complete the existing transportation request.",[],self.tools)
        self.assertEqual(x["status"],"unchanged")
        self.assertIn("not invalidated",x["intervention"])
    def test_missing_history_no_guess(self):
        x=build_ledger([],"Current transportation style preference: scenic_route.",[],self.tools)
        self.assertEqual(x["status"],"unknown")
        self.assertIsNone(x["intervention"])
    def test_unparseable_current_no_guess(self):
        x=build_ledger(self.history,"User says go ahead",[],self.tools)
        self.assertEqual(x["status"],"unknown")
        self.assertIsNone(x["intervention"])
    def test_last_observed_style_not_first(self):
        hist=self.history+[{"role":"assistant","tool_calls":[{"function":{"name":"Decide_Transportation_Preference","arguments":'{"TransportationStyle":"scenic_route"}'}}]}]
        x=build_ledger(hist,"Current transportation style preference: scenic_route.",[],self.tools)
        self.assertEqual(x["status"],"unchanged")
if __name__=="__main__":unittest.main()
