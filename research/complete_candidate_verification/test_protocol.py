from __future__ import annotations
import asyncio, json, tempfile, unittest
from pathlib import Path
from .policy_input import build_policy_input, build_policy_input_from_trace, reconstruct_observed_state
from .submitted_plan_checker import check_submitted_path, select_strictly_better_plan
from .candidate_generator import CandidateGenerator
from .update_controller import run_update
from .committed_plan_executor import CommittedPlanExecutor, PlanExecutionError
from .costbench_adapter import CostBenchNativeExecutionAdapter
from .scoring_logging import (balanced_accuracy, pair_accuracy, score_trajectory,
                              append_jsonl_durable, write_json_atomic)
from .dry_run import run_dry_run, interface

def tools():
    return [
        interface("Acquire_A", ["Start"], "A", 2.0),
        interface("Finish_A", ["A"], "Goal", 4.0),
        interface("Acquire_B", ["Start"], "B", 0.5),
        interface("Finish_B", ["B"], "Goal", 1.0),
        interface("Finish_A_Cheap", ["A"], "Goal", 1.0),
        interface("Out_Of_Path", ["Start"], "Outside", 0.1),
        interface("Finish_Outside", ["Outside"], "Goal", 0.1),
    ]

def policy(old=None, interfaces=None):
    return build_policy_input(task="dining", user_request="Complete the requested task.",
        goal_type="Goal", observed_state_types=["Start"],
        old_remaining_plan=old or ["Acquire_A", "Finish_A"],
        current_tool_interfaces=interfaces or tools(), checkpoint_id="checkpoint-1")

class PolicyInputTests(unittest.TestCase):
    def test_whitelist_rejects_evaluation_fields(self):
        with self.assertRaisesRegex(ValueError, "evaluation-only"):
            build_policy_input(task="dining", user_request="x", goal_type="Goal",
                observed_state_types=["Start"], old_remaining_plan=["Acquire_A","Finish_A"],
                current_tool_interfaces=tools(), checkpoint_id="x",
                source_record={"condition":"SWITCH"})
    def test_fresh_payload_excludes_incumbent(self):
        item=policy()
        self.assertNotIn("incumbent_remaining_plan",item.prompt_payload(False))
        self.assertIn("incumbent_remaining_plan",item.prompt_payload(True))
    def test_failed_tool_does_not_advance_state(self):
        state=reconstruct_observed_state(["Start"],
            [{"tool_name":"Acquire_A","success":False}],tools())
        self.assertEqual(state,("Start",))
    def test_trace_after_failure_rejected(self):
        with self.assertRaisesRegex(ValueError,"after a failed"):
            reconstruct_observed_state(["Start"],[
                {"tool_name":"Acquire_A","success":False},
                {"tool_name":"Finish_A","success":True}],tools())
    def test_state_uses_successful_native_output(self):
        item=build_policy_input_from_trace(task="dining",user_request="x",goal_type="Goal",
            initial_state_types=["Start"],
            successful_tool_trace=[{"tool_name":"Acquire_A","success":True}],
            old_remaining_plan=["Finish_A"],current_tool_interfaces=tools(),checkpoint_id="x")
        self.assertEqual(item.current_state_types,("A","Start"))

class PathCheckerTests(unittest.TestCase):
    def test_complete_path(self):
        r=check_submitted_path(["Start"],"Goal",["Acquire_A","Finish_A"],tools())
        self.assertTrue(r.valid); self.assertEqual(r.cost,6.0)
    def test_same_first_action_better_suffix_switches(self):
        item=policy()
        r=check_submitted_path(item.current_state_types,item.goal_type,
            ["Acquire_A","Finish_A_Cheap"],item.tool_interfaces)
        s=select_strictly_better_plan(item,[["Acquire_A","Finish_A_Cheap"]])
        self.assertTrue(r.valid); self.assertEqual(s.action,"SWITCH")
    def test_invalid_precondition_rejected(self):
        r=check_submitted_path(["Start"],"Goal",["Finish_A"],tools())
        self.assertFalse(r.valid); self.assertIn("missing_preconditions",r.error_text)
    def test_out_of_incumbent_path_can_be_submitted(self):
        item=policy()
        r=check_submitted_path(item.current_state_types,item.goal_type,
            ["Out_Of_Path","Finish_Outside"],item.tool_interfaces)
        self.assertTrue(r.valid); self.assertEqual(r.cost,0.2)
    def test_tie_preserves_incumbent(self):
        item=policy()
        s=select_strictly_better_plan(item,[["Acquire_A","Finish_A"]])
        self.assertEqual(s.action,"RETAIN"); self.assertEqual(s.selected_plan,item.old_remaining_plan)
    def test_invalid_incumbent_without_candidate_stops(self):
        item=policy(old=["Missing_Tool"])
        self.assertEqual(select_strictly_better_plan(item,[]).action,"STOP")

class CandidateGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_sources_and_budget(self):
        seen=[]
        async def fake(**kwargs):
            seen.append(kwargs["messages"]); return {"plan":["Acquire_A","Finish_A"]}
        gen=CandidateGenerator(fake); item=policy()
        await gen.generate_repair(item); await gen.generate_fresh(item)
        with self.assertRaisesRegex(RuntimeError,"budget_exhausted"):
            await gen.generate_revision(item,None,("invalid path",))
        self.assertIn("incumbent_remaining_plan",json.loads(seen[0][1]["content"]))
        self.assertNotIn("incumbent_remaining_plan",json.loads(seen[1][1]["content"]))
        self.assertEqual(gen.calls_used,2)
    async def test_revision_requires_feedback(self):
        async def fake(**kwargs): return {"plan":["Acquire_A","Finish_A"]}
        with self.assertRaisesRegex(ValueError,"concrete"):
            await CandidateGenerator(fake).generate_revision(policy(),None,())

class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_strict_better_candidate_switches(self):
        responses=[{"plan":["Acquire_A","Finish_A"]},{"plan":["Acquire_B","Finish_B"]}]
        calls=0
        async def fake(**kwargs):
            nonlocal calls
            v=responses[calls]; calls+=1; return v
        d=await run_update(policy(),fake)
        self.assertEqual(d.action,"SWITCH")
        self.assertEqual(d.selected_plan,("Acquire_B","Finish_B"))
        self.assertEqual(d.planning_calls,2)
    async def test_third_call_only_repairs_structural_error(self):
        responses=[{"plan":["Finish_A"]},{"plan":["Acquire_A","Finish_A"]},
                   {"plan":["Acquire_B","Finish_B"]}]
        calls=0
        async def fake(**kwargs):
            nonlocal calls
            v=responses[calls]; calls+=1; return v
        d=await run_update(policy(),fake)
        self.assertEqual(d.action,"SWITCH"); self.assertEqual(d.planning_calls,3)
    async def test_valid_tie_does_not_trigger_third_call(self):
        async def fake(**kwargs): return {"plan":["Acquire_A","Finish_A"]}
        d=await run_update(policy(),fake)
        self.assertEqual(d.action,"RETAIN"); self.assertEqual(d.planning_calls,2)

class ExecutorTests(unittest.TestCase):
    def test_exact_order_and_cursor(self):
        item=policy(); ex=CommittedPlanExecutor(item,["Acquire_B","Finish_B"]); state={"Start"}
        self.assertEqual(ex.next_tool(state,item.tool_interfaces),"Acquire_B")
        state.add("B")
        self.assertEqual(ex.record_tool_result(tool_name="Acquire_B",success=True,
            observed_state_types=state,current_tool_interfaces=item.tool_interfaces),"ADVANCED")
        self.assertEqual(ex.next_tool(state,item.tool_interfaces),"Finish_B")
        state.add("Goal")
        self.assertEqual(ex.record_tool_result(tool_name="Finish_B",success=True,
            observed_state_types=state,current_tool_interfaces=item.tool_interfaces),"GOAL_REACHED")
        self.assertTrue(ex.finished)
    def test_failure_does_not_advance(self):
        item=policy(); ex=CommittedPlanExecutor(item,["Acquire_B","Finish_B"])
        result=ex.record_tool_result(tool_name="Acquire_B",success=False,
            observed_state_types=["Start"],current_tool_interfaces=item.tool_interfaces)
        self.assertEqual(result,"REPLAN_REQUIRED"); self.assertEqual(ex.cursor,0)
        self.assertTrue(ex.invalidated)
    def test_tool_change_invalidates(self):
        item=policy(); ex=CommittedPlanExecutor(item,["Acquire_B","Finish_B"])
        changed=tools(); changed[2]=interface("Acquire_B",["Start"],"B",0.6)
        with self.assertRaisesRegex(PlanExecutionError,"catalogue changed"):
            ex.next_tool(["Start"],changed)
        self.assertTrue(ex.invalidated)
    def test_argument_validation(self):
        item=policy(); ex=CommittedPlanExecutor(item,["Acquire_B","Finish_B"])
        self.assertEqual(ex.validate_arguments("Acquire_B",'{"Start":"OBS-1"}'),{"Start":"OBS-1"})
        with self.assertRaisesRegex(PlanExecutionError,"missing required"):
            ex.validate_arguments("Acquire_B","{}")
    def test_native_adapter_waits_for_real_state_update(self):
        item=policy(); ex=CommittedPlanExecutor(item,["Acquire_B","Finish_B"])
        state={"Start"}
        def native_execute(**kwargs): return "native observation"
        adapter=CostBenchNativeExecutionAdapter(ex,native_execute,lambda:state,lambda:item.tool_interfaces)
        class FakeTool:
            name="Acquire_B"; input_types=["Start"]; output_type="B"
        result=adapter.execute(tool_obj=FakeTool(),arguments_str='{"Start":"OBS-1"}',
            refinement_level=2,available_tools={})
        self.assertEqual(result,"native observation")
        self.assertEqual(ex.cursor,0)
        state.add("B")
        self.assertEqual(adapter.confirm_observed_state(),"ADVANCED")
        self.assertEqual(ex.cursor,1)

class ScoringTests(unittest.TestCase):
    def test_ba_and_pair_accuracy(self):
        rows=[
            score_trajectory(task_id="t1",condition="RETAIN",decision="RETAIN",goal_reached=True,
                executed_path=["Acquire_A","Finish_A"],incumbent_path=["Acquire_A","Finish_A"],
                current_tool_costs={"Acquire_A":2,"Finish_A":4},oracle_optimal_value=6),
            score_trajectory(task_id="t1",condition="SWITCH",decision="SWITCH",goal_reached=True,
                executed_path=["Acquire_B","Finish_B"],incumbent_path=["Acquire_A","Finish_A"],
                current_tool_costs={"Acquire_A":2,"Finish_A":4,"Acquire_B":0.5,"Finish_B":1},
                oracle_optimal_value=1.5)]
        self.assertEqual(balanced_accuracy(rows),1.0)
        self.assertEqual(pair_accuracy(rows),1.0)
    def test_durable_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"rows.jsonl"; append_jsonl_durable(p,{"ok":True})
            self.assertEqual(len(p.read_text().splitlines()),1)
            out=Path(tmp)/"summary.json"; write_json_atomic(out,{"status":"ok"})
            self.assertEqual(json.loads(out.read_text())["status"],"ok")

class DryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_free_dry_run(self):
        r=await run_dry_run()
        self.assertEqual(r["provider_calls"],0); self.assertEqual(r["status"],"passed")

if __name__=="__main__":
    unittest.main()
