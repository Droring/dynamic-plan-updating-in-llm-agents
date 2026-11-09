"""Tests for prospective Agent-authored plan extraction and public evidence validation."""
import unittest

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/costbench_method_studies/plan_commitment_evidence_gate"))
from core import ToolSpec
from research.costbench_method_studies.plan_commitment_evidence_gate.plan_memory import recover_pre_event_commitment,public_blocks

def spec(name,inputs,output,cost=1):
    return ToolSpec(name,frozenset(inputs),output,cost)

def toy():
    return {
       "Decide_Test_Preference":spec("Decide_Test_Preference",["X"],"P"),
       "Search_Test_Candidates":spec("Search_Test_Candidates",["P"],"Raw"),
       "Test_Refinement_Step1":spec("Test_Refinement_Step1",["Raw"],"R1"),
       "Test_Refinement_Step2":spec("Test_Refinement_Step2",["R1"],"R2"),
       "Select_Final_Test":spec("Select_Final_Test",["R2"],"Goal"),
       "Test_Search_Planning_to_Step2":spec("Test_Search_Planning_to_Step2",["P"],"R2",4),
       "Test_Preference_and_Search":spec("Test_Preference_and_Search",["X"],"Raw",3),
       "Test_Search_to_Final_4Steps":spec("Test_Search_to_Final_4Steps",["P"],"Goal",6),
       "Test_Finish_from_Step1_3Steps":spec("Test_Finish_from_Step1_3Steps",["Raw"],"Goal",4),
       "Test_Full_Planning_to_Step2":spec("Test_Full_Planning_to_Step2",["X"],"R2",5),
    }

class PlanMemoryTests(unittest.TestCase):
    def test_public_span_mapping_is_pure_dependency_based(self):
        blocks=public_blocks(toy())
        self.assertEqual(blocks["BCD"],("Test_Search_Planning_to_Step2",))
        self.assertEqual(blocks["AB"],("Test_Preference_and_Search",))
        self.assertEqual(blocks["BCDE"],("Test_Search_to_Final_4Steps",))

    def test_explicit_pre_event_model_plan_is_recovered(self):
        t=toy()
        content="Several options exist. The lowest-cost path is A → BCD → E. Executing now."
        m=recover_pre_event_commitment(content,t,["Decide_Test_Preference"],
                                       frozenset({"X","P"}),frozenset({"Goal"}))
        self.assertEqual(m.status,"VALID_PRE_EVENT_COMMITMENT")
        self.assertEqual(m.full_path,("Decide_Test_Preference","Test_Search_Planning_to_Step2","Select_Final_Test"))
        self.assertEqual(m.remaining_path,("Test_Search_Planning_to_Step2","Select_Final_Test"))
        self.assertIn("lowest-cost",m.evidence)

    def test_table_row_is_not_a_committed_plan(self):
        content="| 1 | A → BCD → E | 50.01 |\n| 2 | AB → CDE | 50.02 |"
        m=recover_pre_event_commitment(content,toy(),["Decide_Test_Preference"],
                                       frozenset({"X","P"}),frozenset({"Goal"}))
        self.assertNotEqual(m.status,"VALID_PRE_EVENT_COMMITMENT")

    def test_bad_first_native_step_is_not_rewritten(self):
        m=recover_pre_event_commitment("Selected path: A → BCD → E",toy(),
                                       ["Test_Preference_and_Search"],
                                       frozenset({"Raw"}),frozenset({"Goal"}))
        self.assertEqual(m.status,"NO_VALID_COMMITTED_PATH")

    def test_feasible_graph_cannot_create_a_commitment_from_blank_text(self):
        m=recover_pre_event_commitment("",toy(),["Decide_Test_Preference"],
                                       frozenset({"P"}),frozenset({"Goal"}))
        self.assertNotEqual(m.status,"VALID_PRE_EVENT_COMMITMENT")

    def test_explicit_named_tools_can_be_used(self):
        content=("Chosen path: `Decide_Test_Preference` → "
                 "`Test_Search_Planning_to_Step2` → `Select_Final_Test`.")
        m=recover_pre_event_commitment(content,toy(),["Decide_Test_Preference"],
                                       frozenset({"P"}),frozenset({"Goal"}))
        self.assertEqual(m.status,"VALID_PRE_EVENT_COMMITMENT")

    def test_no_lookup_of_hidden_reference(self):
        # Model text only gives start tool: never synthesize remaining shortest path.
        m=recover_pre_event_commitment("I will use `Decide_Test_Preference` first.",
                                       toy(),["Decide_Test_Preference"],
                                       frozenset({"P"}),frozenset({"Goal"}))
        self.assertNotEqual(m.status,"VALID_PRE_EVENT_COMMITMENT")

    def test_ambiguous_conflicting_selected_paths_abstain(self):
        content=("The cheapest path is A → BCD → E. "
                 "The chosen path is A → B → C → D → E.")
        m=recover_pre_event_commitment(content,toy(),["Decide_Test_Preference"],
                                       frozenset({"P"}),frozenset({"Goal"}))
        self.assertEqual(m.status,"UNPARSEABLE_OR_AMBIGUOUS")


if __name__=="__main__":
    unittest.main()
