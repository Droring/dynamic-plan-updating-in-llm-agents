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


from contextlib import contextmanager
from typing import Iterator


class CostBenchAdapterHook:
    """Temporarily enforce the executor inside the official CostBench run loop.

    Install for one sequential native trajectory. Calls before a plan is
    committed continue through the original helper. Once activated, native
    calls are checked against the committed cursor. The blocker state setter
    confirms successful state updates before the next model turn.
    """

    def __init__(self, official_run: Any, blocker_class: Any) -> None:
        self.official_run = official_run
        self.blocker_class = blocker_class
        self.original_execute = official_run._execute_tool_simulation
        self.original_set_state = blocker_class.set_current_state
        self.adapter: CostBenchNativeExecutionAdapter | None = None
        self.blocker: Any = None
        self._installed = False

    @contextmanager
    def installed(self) -> Iterator["CostBenchAdapterHook"]:
        if self._installed:
            raise RuntimeError("CostBench adapter hook is already installed")
        self._installed = True

        def execute_wrapper(*args: Any, **kwargs: Any) -> str:
            if self.adapter is None:
                return self.original_execute(*args, **kwargs)
            return self.adapter.execute(*args, **kwargs)

        def state_wrapper(blocker: Any, state: set[str]) -> Any:
            result = self.original_set_state(blocker, state)
            self.blocker = blocker
            if self.adapter is not None and self.adapter.pending_success is not None:
                self.adapter.confirm_observed_state()
            return result

        self.official_run._execute_tool_simulation = execute_wrapper
        self.blocker_class.set_current_state = state_wrapper
        try:
            yield self
        finally:
            self.official_run._execute_tool_simulation = self.original_execute
            self.blocker_class.set_current_state = self.original_set_state
            self.adapter = None
            self.blocker = None
            self._installed = False

    def activate(
        self,
        executor: CommittedPlanExecutor,
        interfaces_supplier: Callable[[], list[Mapping[str, Any]]],
    ) -> CostBenchNativeExecutionAdapter:
        if not self._installed:
            raise RuntimeError("install the hook before activating a committed plan")
        if self.blocker is None:
            raise RuntimeError("CostBench blocker state has not been initialized")
        self.adapter = CostBenchNativeExecutionAdapter(
            executor=executor,
            native_execute=self.original_execute,
            state_supplier=lambda: set(self.blocker.current_state),
            interfaces_supplier=interfaces_supplier,
        )
        return self.adapter
