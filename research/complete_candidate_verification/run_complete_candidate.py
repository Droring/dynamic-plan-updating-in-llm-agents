"""End-to-end complete-candidate replanning on native CostBench tools.

The module is provider-agnostic. DeepSeek-compatible call adapters are supplied,
but tests and the phase-one native smoke test use deterministic local responses.
No API key or billable model call is needed for the offline path.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .committed_plan_executor import CommittedPlanExecutor, PlanExecutionError
from .errors import BudgetExceeded, NativeOutcomeUnknown, ProviderOutcomeUnknown
from .policy_input import PolicyInput, build_policy_input
from .scoring_logging import append_jsonl_durable, write_json_atomic
from .update_controller import UpdateDecision, run_update

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_TOOL_STEPS = 7
REFINEMENT_LEVEL = 2
ERROR_PREFIXES = ("[ERROR]", "Tool execution failed", "Error:")


@dataclass(frozen=True)
class NativeExecutionResult:
    success: bool
    observation: str
    output_type: str | None
    output_id: str | None
    raw_output_type: str | None
    error: str | None = None


@dataclass(frozen=True)
class CompleteCandidateRun:
    status: str
    decision: UpdateDecision
    executed_path: tuple[str, ...]
    trace: tuple[Mapping[str, Any], ...]
    goal_reached: bool
    final_state_types: tuple[str, ...]
    planning_calls: int
    parameter_calls: int
    planning_tokens: int
    parameter_tokens: int
    decision_latency_seconds: float
    execution_latency_seconds: float
    error: str | None
    executor_record: Mapping[str, Any] | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision.action,
            "candidate_strategy": self.decision.candidate_strategy,
            "decision_reason": self.decision.reason,
            "selected_plan": list(self.decision.selected_plan or ()),
            "incumbent_plan": list(self.decision.incumbent_check.path),
            "executed_path": list(self.executed_path),
            "trace": [dict(row) for row in self.trace],
            "goal_reached": self.goal_reached,
            "final_state_types": list(self.final_state_types),
            "planning_calls": self.planning_calls,
            "parameter_calls": self.parameter_calls,
            "total_model_calls": self.planning_calls + self.parameter_calls,
            "planning_tokens": self.planning_tokens,
            "parameter_tokens": self.parameter_tokens,
            "total_tokens": self.planning_tokens + self.parameter_tokens,
            "decision_latency_seconds": self.decision_latency_seconds,
            "execution_latency_seconds": self.execution_latency_seconds,
            "error": self.error,
            "executor_record": dict(self.executor_record) if self.executor_record else None,
            "candidate_proposals": [
                {
                    "source": item.source,
                    "path": list(item.path) if item.path is not None else None,
                    "call_index": item.call_index,
                    "prompt_sha256": item.prompt_sha256,
                    "prompt_messages": [dict(message) for message in item.prompt_messages],
                    "response_sha256": item.response_sha256,
                    "raw_response": item.raw_response,
                    "provider_tokens": item.provider_tokens,
                    "elapsed_seconds": item.elapsed_seconds,
                    "error": item.error,
                }
                for item in self.decision.proposals
            ],
            "candidate_checks": [
                {
                    "path": list(item.path),
                    "valid": item.valid,
                    "feasible": item.feasible,
                    "complete": item.complete,
                    "value": item.cost,
                    "errors": list(item.errors),
                }
                for item in self.decision.candidate_checks
            ],
        }


def _response_usage(response: Any) -> int:
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    value = usage.get("total_tokens", 0) if isinstance(usage, dict) else getattr(usage, "total_tokens", 0)
    return int(value or 0)


def _first_message(response: Any) -> Any:
    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if not choices:
        raise ValueError("model response contains no choices")
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
    if message is None:
        raise ValueError("model response contains no assistant message")
    return message


def _message_tool_calls(message: Any) -> list[Any]:
    calls = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    return list(calls or [])


def _call_field(call: Any, key: str) -> Any:
    return call.get(key) if isinstance(call, dict) else getattr(call, key, None)


def _function_field(call: Any, key: str) -> Any:
    function = _call_field(call, "function")
    return function.get(key) if isinstance(function, dict) else getattr(function, key, None)


def _argument_payload(response: Any, expected_tool: str) -> tuple[str, str, int]:
    message = _first_message(response)
    calls = _message_tool_calls(message)
    if len(calls) != 1:
        raise ValueError("parameter response must contain exactly one tool call")
    call = calls[0]
    name = _function_field(call, "name")
    arguments = _function_field(call, "arguments")
    if name != expected_tool:
        raise ValueError(f"parameter response called {name!r}, expected committed tool {expected_tool!r}")
    if not isinstance(arguments, str):
        raise ValueError("parameter response arguments must be a JSON string")
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("parameter response arguments are not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("parameter response arguments must decode to an object")
    return name, arguments, _response_usage(response)


def deepseek_candidate_completion(client: Any, *, model: str = DEFAULT_MODEL,
                                  thinking: str = "disabled") -> Callable[..., Any]:
    """Return the candidate-generator callback for an OpenAI-compatible DeepSeek client."""
    async def complete(*, messages, response_format, max_tokens):
        return await client.chat.completions.create(
            model=model, messages=messages, temperature=0, max_tokens=max_tokens,
            response_format=response_format,
            extra_body={"thinking": {"type": thinking}},
        )
    return complete


def deepseek_argument_completion(client: Any, *, model: str = DEFAULT_MODEL,
                                 thinking: str = "disabled") -> Callable[..., Any]:
    """Return the argument-generation callback; only the committed next tool is exposed."""
    async def complete(*, messages, tools, tool_choice, max_tokens):
        return await client.chat.completions.create(
            model=model, messages=messages, temperature=0, max_tokens=max_tokens,
            tools=tools, tool_choice=tool_choice, parallel_tool_calls=False,
            extra_body={"thinking": {"type": thinking}},
        )
    return complete


def execute_native_tool_with_capture(official_run: Any, *, tool_obj: Any,
                                     arguments_str: str, refinement_level: int,
                                     available_tools: Mapping[str, Any]) -> NativeExecutionResult:
    """Call the pinned official helper and capture its actual native output object."""
    captured: dict[str, Any] = {}
    original_execute = tool_obj.execute

    def capture_execute(*args, **kwargs):
        output = original_execute(*args, **kwargs)
        captured["output"] = output
        return output

    tool_obj.execute = capture_execute
    try:
        observation = official_run._execute_tool_simulation(
            tool_obj=tool_obj, arguments_str=arguments_str,
            refinement_level=refinement_level, available_tools=dict(available_tools),
        )
    finally:
        tool_obj.execute = original_execute

    success = not (
        observation is None
        or (isinstance(observation, str) and observation.startswith(ERROR_PREFIXES))
    )
    if not success:
        return NativeExecutionResult(False, str(observation), None, None, None, str(observation))
    raw = captured.get("output")
    if raw is None:
        return NativeExecutionResult(False, str(observation), None, None, None,
                                     "official helper succeeded without a captured native output")
    raw_type = type(raw).__name__
    output_id = getattr(raw, "unique_id", None)
    if output_id is None:
        getter = getattr(raw, "get_unique_id", None)
        output_id = getter() if callable(getter) else None
    return NativeExecutionResult(True, str(observation), getattr(tool_obj, "output_type", None),
                                 str(output_id) if output_id is not None else None, raw_type)


async def run_complete_candidate(
    policy_input: PolicyInput, *, candidate_completion: Callable[..., Any],
    argument_completion: Callable[..., Any],
    native_execute: Callable[..., NativeExecutionResult],
    native_tool_objects: Mapping[str, Any] | None = None,
    max_argument_tokens: int = DEFAULT_MAX_TOKENS,
    candidate_strategy: str = "repair_plus_fresh",
    max_tool_steps: int = DEFAULT_MAX_TOOL_STEPS,
    native_system_prompt: str | None = None,
) -> CompleteCandidateRun:
    """Generate two full candidates, select, commit, and execute the exact path."""
    if max_tool_steps <= 0:
        raise ValueError("max_tool_steps must be positive")
    decision_start = time.perf_counter()
    decision = await run_update(policy_input, candidate_completion, candidate_strategy)
    decision_latency = time.perf_counter() - decision_start
    planning_tokens = sum(item.provider_tokens for item in decision.proposals)

    if decision.selected_plan is None:
        return CompleteCandidateRun(
            "stopped_without_feasible_plan", decision, (), (), False,
            policy_input.current_state_types, decision.planning_calls, 0,
            planning_tokens, 0, decision_latency, 0.0, decision.reason, None,
        )

    if len(decision.selected_plan) > max_tool_steps:
        return CompleteCandidateRun(
            "plan_exceeds_tool_step_limit", decision, (), (), False,
            policy_input.current_state_types, decision.planning_calls, 0,
            planning_tokens, 0, decision_latency, 0.0,
            f"selected plan has {len(decision.selected_plan)} tools; limit is {max_tool_steps}",
            None,
        )

    executor = CommittedPlanExecutor(policy_input, decision.selected_plan)
    state = set(policy_input.current_state_types)
    controller_instruction = (
        "The controller commits a complete plan before execution. Follow only the "
        "committed next tool, do not choose another tool, and use identifiers found "
        "in the original request or exact native observations."
    )
    system_content = (
        native_system_prompt.strip() + "\n\n" + controller_instruction
        if native_system_prompt and native_system_prompt.strip()
        else "Reach the requested goal from the supplied checkpoint. " + controller_instruction
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": json.dumps({
            "task": policy_input.task, "user_request": policy_input.user_request,
            "goal_type": policy_input.goal_type, "current_state_types": sorted(state),
            "checkpoint_id": policy_input.checkpoint_id,
            "instruction": "Continue from this checkpoint. Use only identifiers and values present in the original request or native tool observations.",
        }, ensure_ascii=False, sort_keys=True)},
    ]
    for history_index, item in enumerate(policy_input.observation_history, start=1):
        call_id = f"checkpoint_tool_call_{history_index}"
        messages.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                "function": {"name": item["tool_name"],
                             "arguments": json.dumps(item["arguments"], ensure_ascii=False, sort_keys=True)}}],
        })
        messages.append({
            "role": "tool", "tool_call_id": call_id, "name": item["tool_name"],
            "content": item["observation"],
        })
        messages.append({
            "role": "user",
            "content": json.dumps({"confirmed_native_output": {
                "tool_name": item["tool_name"], "output_type": item["output_type"],
                "output_id": item["output_id"]}}, ensure_ascii=False, sort_keys=True),
        })
    executed: list[str] = []
    trace: list[Mapping[str, Any]] = []
    parameter_calls = 0
    parameter_tokens = 0
    execution_start = time.perf_counter()
    error = None
    status = "execution_incomplete"

    for step_index in range(len(decision.selected_plan)):
        expected_tool = executor.next_tool(state, policy_input.tool_interfaces)
        request = executor.build_argument_request(messages, state, policy_input.tool_interfaces)
        response = None
        tool_name = None
        arguments_str = None
        arguments = None
        native_call_started = False
        prompt_sha = hashlib.sha256(json.dumps(
            request["messages"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        tokens_before = parameter_tokens
        try:
            parameter_calls += 1
            response = argument_completion(
                messages=request["messages"], tools=request["tools"],
                tool_choice=request["tool_choice"], max_tokens=max_argument_tokens,
            )
            if hasattr(response, "__await__"):
                response = await response
            parameter_tokens += _response_usage(response)
            tool_name, arguments_str, _ = _argument_payload(response, expected_tool)
            arguments = executor.validate_arguments(tool_name, arguments_str)
            native_call_started = True
            native_result = native_execute(
                tool_name=tool_name, arguments_str=arguments_str,
                arguments=arguments,
                available_tools=dict(native_tool_objects or {}),
            )
            if hasattr(native_result, "__await__"):
                native_result = await native_result
            if not isinstance(native_result, NativeExecutionResult):
                raise TypeError("native_execute must return NativeExecutionResult")
        except (BudgetExceeded, ProviderOutcomeUnknown, NativeOutcomeUnknown):
            raise
        except Exception as exc:
            if native_call_started:
                raise NativeOutcomeUnknown(
                    f"native call outcome is uncertain for {expected_tool}: {type(exc).__name__}: {exc}"
                ) from exc
            error = f"{type(exc).__name__}: {exc}"
            executor.invalidate("argument_or_native_execution_exception")
            status = "execution_error"
            trace.append({
                "step": step_index + 1,
                "expected_tool": expected_tool,
                "tool_name": tool_name,
                "arguments": arguments,
                "state_before": sorted(state),
                "parameter_prompt_sha256": prompt_sha,
                "parameter_prompt_messages": request["messages"],
                "parameter_tool_schema": request["tools"],
                "parameter_tool_choice": request["tool_choice"],
                "parameter_tokens": parameter_tokens - tokens_before,
                "native_call_started": native_call_started,
                "native_outcome": "unknown" if native_call_started else "not_started",
                "error": error,
            })
            break

        state_before = sorted(state)
        executed.append(tool_name)
        trace.append({
            "step": step_index + 1, "tool_name": tool_name, "arguments": arguments,
            "state_before": state_before,
            "parameter_prompt_sha256": prompt_sha,
            "parameter_prompt_messages": request["messages"],
            "parameter_tool_schema": request["tools"],
            "parameter_tool_choice": request["tool_choice"],
            "parameter_tokens": parameter_tokens - tokens_before,
            "success": native_result.success, "observation": native_result.observation,
            "output_type": native_result.output_type, "output_id": native_result.output_id,
            "raw_output_type": native_result.raw_output_type, "error": native_result.error,
        })
        call_id = f"committed_tool_call_{step_index + 1}"
        messages.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                "function": {"name": tool_name, "arguments": arguments_str}}],
        })
        messages.append({
            "role": "tool", "tool_call_id": call_id, "name": tool_name,
            "content": native_result.observation,
        })
        if native_result.success:
            messages.append({
                "role": "user",
                "content": json.dumps({"confirmed_native_output": {
                    "tool_name": tool_name, "output_type": native_result.output_type,
                    "output_id": native_result.output_id}}, ensure_ascii=False, sort_keys=True),
            })

        if not native_result.success:
            trace[-1] = {**trace[-1], "state_after": sorted(state)}
            try:
                executor.record_tool_result(tool_name=tool_name, success=False,
                    observed_state_types=state,
                    current_tool_interfaces=policy_input.tool_interfaces)
            except PlanExecutionError as exc:
                error = str(exc)
            status = "native_tool_failed"
            break

        if native_result.raw_output_type != native_result.output_type:
            trace[-1] = {**trace[-1], "state_after": sorted(state)}
            executor.invalidate("native_output_type_mismatch")
            error = (f"native output type mismatch: {native_result.raw_output_type!r} "
                     f"!= {native_result.output_type!r}")
            status = "execution_error"
            break
        state.add(native_result.output_type)
        trace[-1] = {**trace[-1], "state_after": sorted(state)}
        try:
            advancement = executor.record_tool_result(
                tool_name=tool_name, success=True, observed_state_types=state,
                current_tool_interfaces=policy_input.tool_interfaces,
            )
        except PlanExecutionError as exc:
            error = str(exc)
            status = "execution_error"
            break
        if advancement == "GOAL_REACHED":
            status = "goal_reached"
            break
    else:
        if policy_input.goal_type in state:
            status = "goal_reached"
        else:
            status = "plan_exhausted_before_goal"
            executor.invalidate("committed_plan_exhausted_before_goal")

    execution_latency = time.perf_counter() - execution_start
    return CompleteCandidateRun(
        status, decision, tuple(executed), tuple(trace),
        policy_input.goal_type in state, tuple(sorted(state)),
        decision.planning_calls, parameter_calls, planning_tokens, parameter_tokens,
        decision_latency, execution_latency, error, executor.execution_record(),
    )


def make_observation_history(
    prepared: Mapping[str, Any], query: Mapping[str, Any], native: Any,
) -> tuple[Mapping[str, Any], ...]:
    """Build history only from the exact successfully replayed native prefix."""
    if not prepared.get("prefix_name"):
        return ()
    prefix_tool = prepared["tool_objects"][prepared["prefix_name"]]
    prefix_arguments = native.build_prefix_arguments(prefix_tool, query, prepared["task"])
    if not prepared.get("prefix_output_id"):
        raise ValueError("the completed prefix has no native output identifier")
    return ({
        "tool_name": prepared["prefix_name"],
        "arguments": prefix_arguments,
        "observation": prepared["prefix_observation"],
        "output_type": prefix_tool.output_type,
        "output_id": str(prepared["prefix_output_id"]),
    },)


def make_policy_input_from_prepared(
    prepared: Mapping[str, Any],
    observation_history: tuple[Mapping[str, Any], ...] = (),
) -> PolicyInput:
    """Select policy-allowed fields and genuine native observations only."""
    return build_policy_input(
        task=prepared["task"], user_request=prepared["user_request"],
        goal_type=prepared["goal_type"], observed_state_types=prepared["state"],
        old_remaining_plan=prepared["incumbent_suffix"],
        current_tool_interfaces=prepared["tool_interfaces"],
        checkpoint_id=prepared["checkpoint_sha256"],
        observation_history=observation_history,
    )


async def run_native_offline_smoke(prepared: Mapping[str, Any], query: Mapping[str, Any],
                                   native: Any, costbench: Mapping[str, Any],
                                   candidate_strategy: str = "repair_plus_fresh",
                                   max_tool_steps: int = DEFAULT_MAX_TOOL_STEPS) -> CompleteCandidateRun:
    """Execute a complete native trajectory using deterministic mocks and zero API calls."""
    history = make_observation_history(prepared, query, native)
    policy_input = make_policy_input_from_prepared(prepared, history)
    incumbent = list(policy_input.old_remaining_plan)

    class OfflinePlanner:
        def __init__(self):
            self.calls = 0
        async def __call__(self, *, messages, response_format, max_tokens):
            self.calls += 1
            return {"choices": [{"message": {"content": json.dumps({"plan": incumbent})}}],
                    "usage": {"total_tokens": 0}}

    observed_ids: dict[str, str] = {}
    for input_type in policy_input.current_state_types:
        try:
            observed_ids[input_type] = native.query_input_for_type(
                input_type, query, prepared["task"])
        except ValueError:
            if (prepared.get("prefix_name")
                    and input_type == prepared["tool_objects"][prepared["prefix_name"]].output_type
                    and prepared.get("prefix_output_id")):
                observed_ids[input_type] = prepared["prefix_output_id"]

    class OfflineArguments:
        def __init__(self):
            self.calls = 0
        async def __call__(self, *, messages, tools, tool_choice, max_tokens):
            self.calls += 1
            if len(tools) != 1:
                raise AssertionError("argument resolver must see exactly one committed tool")
            function = tools[0]["function"]
            name = function["name"]
            required = function["parameters"]["required"]
            visible_ids = dict(observed_ids)
            for message in messages:
                if message.get("role") == "user":
                    try:
                        metadata = json.loads(message.get("content") or "{}").get("confirmed_native_output")
                    except (TypeError, json.JSONDecodeError):
                        metadata = None
                    if metadata:
                        visible_ids[metadata["output_type"]] = metadata["output_id"]
            missing = [item for item in required if item not in visible_ids]
            if missing:
                raise ValueError(f"no observed identifiers in the prompt for {name}: {missing}")
            arguments = {item: visible_ids[item] for item in required}
            return {"choices": [{"message": {"tool_calls": [{
                "id": f"offline-{self.calls}",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }]}}], "usage": {"total_tokens": 0}}

    def execute(**kwargs):
        name = kwargs["tool_name"]
        result = execute_native_tool_with_capture(
            costbench["official_run"], tool_obj=prepared["tool_objects"][name],
            arguments_str=kwargs["arguments_str"], refinement_level=REFINEMENT_LEVEL,
            available_tools=prepared["tool_objects"],
        )
        if result.success and result.output_type and result.output_id:
            observed_ids[result.output_type] = result.output_id
        return result

    planner, arguments = OfflinePlanner(), OfflineArguments()
    native_system_prompt = native.make_official_system_prompt(
        costbench["official_run"], prepared["task"])
    result = await run_complete_candidate(
        policy_input, candidate_completion=planner, argument_completion=arguments,
        native_execute=execute, native_tool_objects=prepared["tool_objects"],
        candidate_strategy=candidate_strategy,
        max_tool_steps=max_tool_steps,
        native_system_prompt=native_system_prompt,
    )
    if planner.calls != 2:
        raise AssertionError(f"expected two planning calls, got {planner.calls}")
    if arguments.calls != len(result.executed_path):
        raise AssertionError("parameter call count differs from native executed path")
    return result


def load_native_trial(costbench_root: Path, query_id: str | None, condition: str,
                      minimum_plan_length: int = 1):
    native_dir = Path(__file__).resolve().parents[2] / "experiments" / "paired_50" / "native_execution"
    sys.path.insert(0, str(native_dir))
    import run_official_harness as native
    root = costbench_root.resolve()
    os.chdir(root)
    requests, manifest, registry = native.load_frozen_inputs()
    registry_rows = {row["task_id"]: row for row in registry["selection"]["task_ids"]}
    query_path = root / "env" / "data" / "runtime" / "queries" / "queries.json"
    query_rows = json.loads(query_path.read_text(encoding="utf-8"))
    queries = {row["query_id"].strip("<>"): row for row in query_rows}
    costbench = native.load_costbench(root)
    candidates = [
        row for row in requests
        if manifest[row["trial_id"]]["condition"] == condition
        and (query_id is None or row["query_id"] == query_id)
    ]
    if not candidates:
        raise ValueError(f"No frozen {condition} request found for query_id={query_id!r}")
    for request in candidates:
        selected_query_id = request["query_id"]
        prepared = native.prepare_trial(
            request, manifest[request["trial_id"]], queries[selected_query_id],
            registry_rows[selected_query_id], costbench)
        if len(prepared["incumbent_suffix"]) >= minimum_plan_length:
            return native, costbench, prepared, queries[selected_query_id]
    raise ValueError(
        f"No {condition} checkpoint met minimum plan length {minimum_plan_length}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free native CostBench complete-plan smoke test.")
    parser.add_argument("--costbench-root", type=Path, required=True)
    parser.add_argument("--query-id", default=None,
                        help="Optional fixed query ID; by default select a multi-step RETAIN checkpoint.")
    parser.add_argument("--condition", choices=("RETAIN", "SWITCH"), default="RETAIN")
    parser.add_argument("--candidate-strategy",
                        choices=("repair_plus_fresh", "fresh_plus_fresh"),
                        default="repair_plus_fresh")
    parser.add_argument("--max-tool-steps", type=int, default=DEFAULT_MAX_TOOL_STEPS)
    parser.add_argument("--out", type=Path, default=Path("outputs/complete_candidate_offline_smoke"))
    args = parser.parse_args()
    args.costbench_root = args.costbench_root.resolve()
    args.out = args.out.resolve()
    if args.max_tool_steps <= 0:
        raise ValueError("--max-tool-steps must be positive")
    minimum_plan_length = 2 if args.query_id is None else 1
    native, costbench, prepared, query = load_native_trial(
        args.costbench_root, args.query_id, args.condition,
        minimum_plan_length=minimum_plan_length)
    result = asyncio.run(run_native_offline_smoke(
        prepared, query, native, costbench,
        candidate_strategy=args.candidate_strategy, max_tool_steps=args.max_tool_steps))
    record = result.to_record()
    record.update({
        "query_id": prepared["query_id"],
        "condition_for_posthoc_audit_only": args.condition,
        "candidate_strategy": args.candidate_strategy,
        "provider_api_calls": 0,
        "upstream_costbench_revision": costbench["revision"],
    })
    args.out.mkdir(parents=True, exist_ok=True)
    append_jsonl_durable(args.out / "responses.jsonl", record)
    write_json_atomic(args.out / "summary.json", {
        "status": result.status, "provider_api_calls": 0,
        "planning_calls": result.planning_calls, "parameter_calls": result.parameter_calls,
        "goal_reached": result.goal_reached, "executed_path": list(result.executed_path),
        "max_tool_steps": args.max_tool_steps,
    })
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if result.status == "goal_reached" else 2


if __name__ == "__main__":
    raise SystemExit(main())
