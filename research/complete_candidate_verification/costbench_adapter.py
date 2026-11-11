"""Adapter around the pinned CostBench native tool execution helper."""
from __future__ import annotations
from typing import Any, Callable, Mapping
from .committed_plan_executor import CommittedPlanExecutor, PlanExecutionError

ERROR_PREFIXES = ("[ERROR]", "Tool execution failed", "Error:")

class CostBenchNativeExecutionAdapter:
    """Enforce the committed next tool while delegating execution to CostBench.

    Install this adapter around env.run._execute_tool_simulation. The official
    runner still owns the actual state update; confirm_observed_state must be
    called immediately after its blocker.set_current_state update.
    """
    def __init__(self, executor: CommittedPlanExecutor,
                 native_execute: Callable[..., str],
                 state_supplier: Callable[[], set[str]],
                 interfaces_supplier: Callable[[], list[Mapping[str, Any]]]) -> None:
        self.executor = executor
        self.native_execute = native_execute
        self.state_supplier = state_supplier
        self.interfaces_supplier = interfaces_supplier
        self.pending_success: tuple[str, tuple[str, ...]] | None = None

    def execute(self, *, tool_obj: Any, arguments_str: str, refinement_level: int,
                available_tools: Mapping[str, Any]) -> str:
        interfaces = self.interfaces_supplier()
        state_before = set(self.state_supplier())
        expected = self.executor.next_tool(state_before, interfaces)
        if expected != getattr(tool_obj, "name", None):
            self.executor.invalidate("official_runner_requested_tool_outside_committed_plan")
            raise PlanExecutionError("official runner requested a tool outside the committed path")
        self.executor.validate_arguments(expected, arguments_str)
        if not set(tool_obj.input_types).issubset(state_before):
            self.executor.invalidate("native_tool_preconditions_not_met")
            raise PlanExecutionError("native tool preconditions are not satisfied")
        result = self.native_execute(tool_obj=tool_obj, arguments_str=arguments_str,
            refinement_level=refinement_level, available_tools=dict(available_tools))
        success = not (isinstance(result, str) and result.startswith(ERROR_PREFIXES))
        if not success:
            self.executor.record_tool_result(tool_name=expected, success=False,
                observed_state_types=state_before, current_tool_interfaces=interfaces)
            return result
        self.pending_success = (expected, tuple(sorted(state_before | {tool_obj.output_type})))
        return result

    def confirm_observed_state(self) -> str:
        if self.pending_success is None:
            raise PlanExecutionError("no successful native call awaits state confirmation")
        name, expected_state = self.pending_success
        self.pending_success = None
        observed = set(self.state_supplier())
        if tuple(sorted(observed)) != expected_state:
            self.executor.invalidate("official_native_state_update_mismatch")
            raise PlanExecutionError("official CostBench state update differs from native output")
        return self.executor.record_tool_result(tool_name=name, success=True,
            observed_state_types=observed, current_tool_interfaces=self.interfaces_supplier())
