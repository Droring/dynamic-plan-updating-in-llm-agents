#!/usr/bin/env python3
import unittest
from action_evidence_guard import inspect_action, correction_for
TOOLS=[
 {"type":"function","function":{"name":"Decide_Transportation_Preference","parameters":{"required":["LocationPreference","TransportationStyle"]}}},
 {"type":"function","function":{"name":"Transportation_Search_Planning_to_Step2","parameters":{"required":["LocationPreference","TimeInfo","TransportationPreference"]}}},
 {"type":"function","function":{"name":"Transportation_Finish_from_Step1_3Steps","parameters":{"required":["TimeInfo","TransportationCandidate_Raw"]}}},
]
LEDGER={"status":"changed","original_style":"comfort_priority","new_style":"scenic_route"}
STATE={"LocationPreference","TimeInfo","TransportationPreference","TransportationStyle","TransportationTier"}
def c(name,**kw):return [{"tool":name,"arguments":kw}]
class GuardTests(unittest.TestCase):
 def test_reject_old_preference_input(self):
  bad=inspect_action(c("Transportation_Search_Planning_to_Step2",TransportationPreference="PreferenceOld"),
    TOOLS,STATE,LEDGER)
  self.assertEqual(bad[0]["code"],"stale_dependency")
 def test_new_preference_allowed(self):
  self.assertEqual(inspect_action(c("Decide_Transportation_Preference",TransportationStyle="scenic_route"),
   TOOLS,STATE,LEDGER),[])
 def test_reject_wrong_new_preference(self):
  bad=inspect_action(c("Decide_Transportation_Preference",TransportationStyle="comfort_priority"),
   TOOLS,STATE,LEDGER)
  self.assertEqual(bad[0]["code"],"incorrect_updated_fact")
 def test_reject_missing_input(self):
  bad=inspect_action(c("Transportation_Finish_from_Step1_3Steps",TransportationCandidate_Raw="Stale"),
   TOOLS,STATE,{"status":"unchanged"})
  self.assertEqual(bad[0]["code"],"missing_native_prerequisite")
 def test_retain_no_replan(self):
  self.assertEqual(inspect_action(c("Transportation_Search_Planning_to_Step2",TransportationPreference="PreferenceOld"),
    TOOLS,STATE,{"status":"unchanged","original_style":"comfort_priority","new_style":"comfort_priority"}),[])
 def test_refreshed_allows_downstream(self):
  self.assertEqual(inspect_action(c("Transportation_Search_Planning_to_Step2",TransportationPreference="PreferenceNew"),
    TOOLS,STATE,LEDGER,has_refreshed=True),[])
 def test_message_exposes_evidence_not_gold(self):
  msg=correction_for([{"code":"stale_dependency","tool":"Search","current":"scenic_route","prior":"comfort_priority"}])
  self.assertIn("No tool was executed",msg)
  self.assertNotIn("gold",msg)
if __name__=="__main__":unittest.main()
