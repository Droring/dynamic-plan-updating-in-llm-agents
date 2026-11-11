from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from .committed_plan_executor import CommittedPlanExecutor
from .policy_input import build_policy_input
from .run_complete_candidate import (NativeExecutionResult, run_complete_candidate,
    deepseek_candidate_completion, deepseek_argument_completion)
from .errors import NativeOutcomeUnknown, ProviderOutcomeUnknown
from .test_protocol import tools


def make_policy(with_history=False):
    history = ()
    state = ["Start"]
    old_plan = ["Acquire_A", "Finish_A"]
    if with_history:
        state = ["Start", "A"]
        old_plan = ["Finish_A"]
        history = ({
            "tool_name": "Acquire_A",
            "arguments": {"Start": "OBS-START"},
            "observation": "Observed A as OBS-A",
            "output_type": "A",
            "output_id": "OBS-A",
        },)
    return build_policy_input(
        task="dining",
        user_request="Complete the requested task.",
        goal_type="Goal",
        observed_state_types=state,
        old_remaining_plan=old_plan,
        current_tool_interfaces=tools(),
        checkpoint_id="runner-checkpoint",
        observation_history=history,
    )


class CompleteCandidateRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_candidate_switch_and_native_execution(self):
        policy = make_policy(with_history=True)
        plans = [
            {"plan": ["Acquire_B", "Finish_B"]},
        ]
        planner_calls = 0
        planner_messages = []
        observed_ids = {"Start": "OBS-START", "A": "OBS-A"}
        native_outputs = {"Acquire_A": "A", "Finish_A": "Goal",
                          "Acquire_B": "B", "Finish_B": "Goal"}

        async def candidate_completion(**kwargs):
            nonlocal planner_calls
            plan = plans[planner_calls]
            planner_messages.append(kwargs["messages"])
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
            self.assertTrue(any(m.get("role") == "tool" and m.get("content") == "Observed A as OBS-A"
                                for m in messages))
            self.assertTrue(any("OBS-A" in json.dumps(m) for m in messages))
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
            native_system_prompt="Official CostBench system instructions.",
        )
        self.assertEqual(result.status, "goal_reached")
        self.assertEqual(result.decision.action, "SWITCH")
        self.assertEqual(result.decision.candidate_strategy, "fresh_only")
        self.assertEqual(result.executed_path, ("Acquire_B", "Finish_B"))
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.planning_calls, 1)
        self.assertEqual(result.parameter_calls, 2)
        self.assertEqual(result.planning_tokens, 11)
        self.assertEqual(result.parameter_tokens, 14)
        self.assertEqual(planner_calls, 1)
        self.assertEqual(parameter_calls, 2)
        self.assertEqual(len(planner_messages), 1)
        self.assertNotIn(
            "incumbent_remaining_plan",
            json.loads(planner_messages[0][1]["content"]),
        )
        self.assertTrue(result.executor_record["finished"])
        self.assertEqual(result.trace[0]["state_before"], ["A", "Start"])
        self.assertEqual(result.trace[0]["state_after"], ["A", "B", "Start"])
        self.assertIn("Official CostBench system instructions.", result.trace[0]["parameter_prompt_messages"][0]["content"])
        self.assertTrue(result.to_record()["candidate_proposals"][0]["prompt_messages"])
        self.assertEqual(result.trace[0]["parameter_response"]["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "Acquire_B")
        self.assertTrue(result.trace[0]["parameter_response_sha256"])

    async def test_local_substitution_switches_and_executes_without_extra_planning_call(self):
        policy = make_policy(with_history=True)
        planner_calls = 0
        async def candidate_completion(**kwargs):
            nonlocal planner_calls
            planner_calls += 1
            return {
                "choices": [{"message": {"content": json.dumps(
                    {"plan": ["Finish_A"]})}}],
                "usage": {"total_tokens": 11},
            }

        observed_ids = {"Start": "OBS-START", "A": "OBS-A"}
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
                    "id": f"local-{parameter_calls}",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }]}}],
                "usage": {"total_tokens": 7},
            }

        def native_execute(*, tool_name, arguments_str, arguments, available_tools):
            output_id = "OBS-GOAL"
            observed_ids["Goal"] = output_id
            return NativeExecutionResult(True, "Observed Goal", "Goal", output_id, "Goal")

        result = await run_complete_candidate(
            policy, candidate_completion=candidate_completion,
            argument_completion=argument_completion, native_execute=native_execute,
            candidate_strategy="fresh_with_local_substitution",
        )
        self.assertEqual(result.status, "goal_reached")
        self.assertEqual(result.decision.action, "SWITCH")
        self.assertEqual(result.decision.selected_plan, ("Finish_A_Cheap",))
        self.assertEqual(result.executed_path, ("Finish_A_Cheap",))
        self.assertEqual(result.planning_calls, 1)
        self.assertEqual(planner_calls, 1)
        self.assertEqual(parameter_calls, 1)
        self.assertGreaterEqual(len(result.decision.local_substitutions), 1)
        self.assertEqual(
            result.to_record()["local_substitutions"][0]["candidate_path"],
            ["Finish_A_Cheap"],
        )

    async def test_deepseek_adapters_build_expected_nonstreaming_requests(self):
        seen = []
        class FakeCompletions:
            async def create(self, **kwargs):
                seen.append(kwargs)
                return {"choices": [{"message": {"content": '{"plan":["A"]}'}}]}
        client = SimpleNamespace(chat=SimpleNamespace(
            completions=FakeCompletions()
        ))
        candidate = deepseek_candidate_completion(client, model="deepseek-flash")
        await candidate(messages=[{"role": "user", "content": "plan"}],
                        response_format={"type": "json_object"}, max_tokens=128)
        argument = deepseek_argument_completion(client, model="deepseek-flash")
        await argument(messages=[{"role": "user", "content": "args"}],
                       tools=[{"type": "function", "function": {"name": "A"}}],
                       tool_choice="required", max_tokens=64)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["model"], "deepseek-flash")
        self.assertEqual(seen[0]["response_format"], {"type": "json_object"})
        self.assertEqual(seen[0]["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(seen[1]["tool_choice"], "required")
        self.assertFalse(seen[1]["parallel_tool_calls"])
        self.assertEqual(len(seen[1]["tools"]), 1)

    async def test_failed_argument_request_is_counted(self):
        policy = make_policy()
        async def candidate_completion(**kwargs):
            return {"choices": [{"message": {"content": json.dumps(
                {"plan": ["Acquire_A", "Finish_A"]})}}]}
        async def argument_completion(**kwargs):
            raise RuntimeError("offline argument provider failure")
        def native_execute(**kwargs):
            raise AssertionError("native execution must not start")
        result = await run_complete_candidate(
            policy, candidate_completion=candidate_completion,
            argument_completion=argument_completion, native_execute=native_execute,
        )
        self.assertEqual(result.status, "execution_error")
        self.assertEqual(result.parameter_calls, 1)
        self.assertFalse(result.goal_reached)

    async def test_provider_outcome_unknown_propagates_without_retry(self):
        policy = make_policy()
        calls = 0
        async def candidate_completion(**kwargs):
            nonlocal calls
            calls += 1
            raise ProviderOutcomeUnknown("provider timeout")
        async def argument_completion(**kwargs):
            raise AssertionError("argument generation must not start")
        def native_execute(**kwargs):
            raise AssertionError("native execution must not start")
        with self.assertRaisesRegex(ProviderOutcomeUnknown,"provider timeout"):
            await run_complete_candidate(
                policy, candidate_completion=candidate_completion,
                argument_completion=argument_completion, native_execute=native_execute,
            )
        self.assertEqual(calls,1)

    async def test_native_exception_is_marked_as_uncertain_not_retried(self):
        policy = make_policy()
        async def candidate_completion(**kwargs):
            return {"choices": [{"message": {"content": json.dumps(
                {"plan": ["Acquire_A", "Finish_A"]})}}]}
        async def argument_completion(*, messages, tools, tool_choice, max_tokens):
            name=tools[0]["function"]["name"]
            return {"choices": [{"message": {"tool_calls": [{
                "id":"call-uncertain",
                "function":{"name":name,"arguments":'{"Start":"OBS-START"}'},
            }]}}], "usage":{"total_tokens":3}}
        def native_execute(**kwargs):
            raise RuntimeError("connection dropped after native call started")
        with self.assertRaisesRegex(NativeOutcomeUnknown,"outcome is uncertain"):
            await run_complete_candidate(
                policy,candidate_completion=candidate_completion,
                argument_completion=argument_completion,native_execute=native_execute,
            )

    async def test_malformed_argument_response_usage_and_prompt_are_logged(self):
        policy = make_policy()
        async def candidate_completion(**kwargs):
            return {"choices": [{"message": {"content": json.dumps(
                {"plan": ["Acquire_A", "Finish_A"]})}}]}
        async def argument_completion(**kwargs):
            return {"choices": [{"message": {"content": "not a tool call"}}],
                    "usage": {"total_tokens": 13}}
        def native_execute(**kwargs):
            raise AssertionError("native execution must not start")
        result = await run_complete_candidate(
            policy, candidate_completion=candidate_completion,
            argument_completion=argument_completion, native_execute=native_execute,
        )
        self.assertEqual(result.status, "execution_error")
        self.assertEqual(result.parameter_tokens, 13)
        self.assertEqual(len(result.trace), 1)
        self.assertFalse(result.trace[0]["native_call_started"])
        self.assertTrue(result.trace[0]["parameter_prompt_messages"])
        self.assertEqual(result.trace[0]["parameter_response"]["choices"][0]["message"]["content"], "not a tool call")
        self.assertTrue(result.trace[0]["parameter_response_sha256"])

    async def test_selected_plan_over_step_limit_stops_before_native_execution(self):
        policy = make_policy()
        async def candidate_completion(**kwargs):
            return {"choices": [{"message": {"content": json.dumps(
                {"plan": ["Acquire_A", "Finish_A"]})}}]}
        async def argument_completion(**kwargs):
            raise AssertionError("argument generation must not start")
        def native_execute(**kwargs):
            raise AssertionError("native execution must not start")
        result = await run_complete_candidate(
            policy, candidate_completion=candidate_completion,
            argument_completion=argument_completion, native_execute=native_execute,
            max_tool_steps=1,
        )
        self.assertEqual(result.status, "plan_exceeds_tool_step_limit")
        self.assertEqual(result.parameter_calls, 0)
        self.assertFalse(result.goal_reached)

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
