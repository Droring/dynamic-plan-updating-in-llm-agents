from __future__ import annotations

import json
import unittest

from .committed_plan_executor import CommittedPlanExecutor
from .policy_input import build_policy_input
from .run_complete_candidate import NativeExecutionResult, run_complete_candidate
from .test_protocol import tools


def make_policy():
    return build_policy_input(
        task="dining",
        user_request="Complete the requested task.",
        goal_type="Goal",
        observed_state_types=["Start"],
        old_remaining_plan=["Acquire_A", "Finish_A"],
        current_tool_interfaces=tools(),
        checkpoint_id="runner-checkpoint",
    )


class CompleteCandidateRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_candidate_switch_and_native_execution(self):
        policy = make_policy()
        plans = [
            {"plan": ["Acquire_A", "Finish_A"]},
            {"plan": ["Acquire_B", "Finish_B"]},
        ]
        planner_calls = 0
        observed_ids = {"Start": "OBS-START"}
        native_outputs = {"Acquire_A": "A", "Finish_A": "Goal",
                          "Acquire_B": "B", "Finish_B": "Goal"}

        async def candidate_completion(**kwargs):
            nonlocal planner_calls
            plan = plans[planner_calls]
            planner_calls += 1
            return {
                "choices": [{"message": {"content": json.dumps(plan)}}],
                "usage": {"total_tokens": 11},
            }

        parameter_calls = 0
        async def argument_completion(*, messages, tools, tool_choice, max_tokens):
            nonlocal parameter_calls
            parameter_calls += 1
            self.assertEqual(len(tools), 1)
            name = tools[0]["function"]["name"]
            required = tools[0]["function"]["parameters"]["required"]
            arguments = {key: observed_ids[key] for key in required}
            return {
                "choices": [{"message": {"tool_calls": [{
                    "id": f"call-{parameter_calls}",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }]}}],
                "usage": {"total_tokens": 7},
            }

        def native_execute(*, tool_name, arguments_str, arguments, available_tools):
            self.assertTrue(arguments)
            output_type = native_outputs[tool_name]
            output_id = f"OBS-{output_type.upper()}"
            observed_ids[output_type] = output_id
            return NativeExecutionResult(
                True, f"Observed {output_type} as {output_id}",
                output_type, output_id, output_type,
            )

        result = await run_complete_candidate(
            policy,
            candidate_completion=candidate_completion,
            argument_completion=argument_completion,
            native_execute=native_execute,
        )
        self.assertEqual(result.status, "goal_reached")
        self.assertEqual(result.decision.action, "SWITCH")
        self.assertEqual(result.executed_path, ("Acquire_B", "Finish_B"))
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.planning_calls, 2)
        self.assertEqual(result.parameter_calls, 2)
        self.assertEqual(result.planning_tokens, 22)
        self.assertEqual(result.parameter_tokens, 14)
        self.assertEqual(planner_calls, 2)
        self.assertEqual(parameter_calls, 2)

    async def test_native_failure_invalidates_and_does_not_advance(self):
        policy = make_policy()
        calls = 0

        async def candidate_completion(**kwargs):
            nonlocal calls
            calls += 1
            return {"choices": [{"message": {"content": json.dumps(
                {"plan": ["Acquire_A", "Finish_A"]})}}]}

        async def argument_completion(*, messages, tools, tool_choice, max_tokens):
            name = tools[0]["function"]["name"]
            return {"choices": [{"message": {"tool_calls": [{
                "id": "call-1",
                "function": {"name": name, "arguments": '{"Start":"OBS-START"}'},
            }]}}]}

        def native_execute(**kwargs):
            return NativeExecutionResult(
                False, "Tool execution failed: simulated native failure",
                None, None, None, "simulated native failure",
            )

        result = await run_complete_candidate(
            policy,
            candidate_completion=candidate_completion,
            argument_completion=argument_completion,
            native_execute=native_execute,
        )
        self.assertEqual(result.status, "native_tool_failed")
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.executed_path, ("Acquire_A",))
        self.assertEqual(result.final_state_types, ("Start",))
        self.assertEqual(result.parameter_calls, 1)


if __name__ == "__main__":
    unittest.main()
