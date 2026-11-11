"""State-bound complete-plan certificate and cursor-controlled execution."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Any, Iterable, Mapping
from .policy_input import PolicyInput, canonical_json, parse_public_tool_interfaces
from .submitted_plan_checker import check_submitted_path

class PlanExecutionError(RuntimeError):
    pass

@dataclass(frozen=True)
class PlanCertificate:
    checkpoint_id: str
    state_sha256: str
    tool_catalog_sha256: str
    plan_sha256: str
    plan_value: float
    generation: int

class CommittedPlanExecutor:
    """Issue a certificate for one complete plan and enforce its exact tool order."""
    def __init__(self, policy_input: PolicyInput, selected_plan: Iterable[str]) -> None:
        self.policy_input = policy_input
        self.plan = tuple(selected_plan)
        self.contracts = parse_public_tool_interfaces(policy_input.tool_interfaces)
        check = check_submitted_path(policy_input.current_state_types, policy_input.goal_type,
                                     self.plan, policy_input.tool_interfaces)
        if not check.valid or check.cost is None:
            raise ValueError("cannot commit an invalid or incomplete path: " + check.error_text)
        self.current_state = tuple(policy_input.current_state_types)
        self.cursor = 0
        self.generation = 0
        self.invalidated = False
        self.finished = False
        self.invalidation_reason: str | None = None
        self.tool_catalog_sha256 = hashlib.sha256(
            canonical_json(list(policy_input.tool_interfaces)).encode()).hexdigest()
        self.certificate = self._issue(check.cost)

    def _issue(self, remaining_value: float) -> PlanCertificate:
        state_sha = hashlib.sha256(canonical_json(list(self.current_state)).encode()).hexdigest()
        plan_sha = hashlib.sha256(canonical_json(list(self.plan)).encode()).hexdigest()
        self.generation += 1
        return PlanCertificate(self.policy_input.checkpoint_id, state_sha,
            self.tool_catalog_sha256, plan_sha, round(remaining_value, 9), self.generation)

    def invalidate(self, reason: str) -> None:
        self.invalidated = True
        self.invalidation_reason = reason
        self.certificate = None

    def _assert_current(self, current_state_types: Iterable[str],
                        current_tool_interfaces: Iterable[Mapping[str, Any]]) -> None:
        if self.invalidated:
            raise PlanExecutionError("plan certificate is invalid: " + str(self.invalidation_reason))
        state = tuple(sorted(set(current_state_types)))
        if state != self.current_state:
            self.invalidate("observed_state_changed_outside_committed_execution")
            raise PlanExecutionError("observed state differs from the committed plan certificate")
        tools = tuple(dict(x) for x in current_tool_interfaces)
        digest = hashlib.sha256(canonical_json(list(tools)).encode()).hexdigest()
        if digest != self.certificate.tool_catalog_sha256:
            self.invalidate("tool_attributes_or_interfaces_changed")
            raise PlanExecutionError("tool catalogue changed; committed certificate is stale")

    def next_tool(self, current_state_types: Iterable[str],
                  current_tool_interfaces: Iterable[Mapping[str, Any]]) -> str | None:
        self._assert_current(current_state_types, current_tool_interfaces)
        if self.finished:
            return None
        if self.cursor >= len(self.plan):
            self.invalidate("plan_cursor_exhausted_before_goal")
            raise PlanExecutionError("committed path ended before the goal")
        return self.plan[self.cursor]

    def next_tool_interface(self, current_state_types: Iterable[str],
                            current_tool_interfaces: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        name = self.next_tool(current_state_types, current_tool_interfaces)
        if name is None:
            return None
        for interface in current_tool_interfaces:
            if interface.get("function", {}).get("name") == name:
                return dict(interface)
        self.invalidate("next_committed_tool_not_exposed")
        raise PlanExecutionError("next committed tool is no longer exposed")

    def build_argument_request(self, messages: Iterable[Mapping[str, Any]],
                               current_state_types: Iterable[str],
                               current_tool_interfaces: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Constrain the LLM to arguments for the already committed next tool."""
        name = self.next_tool(current_state_types, current_tool_interfaces)
        if name is None:
            return {"tool_name": None, "messages": list(messages), "tools": [],
                    "tool_choice": "none"}
        interface = self.next_tool_interface(current_state_types, current_tool_interfaces)
        prompt = (
            "The complete plan has already been committed by the controller: "
            + " -> ".join(self.plan) + ". Your only task is to produce valid arguments "
            + "for the exact next tool " + name + ". Do not select, replace, reorder, "
            + "or add tools. Use only identifiers and values present in the conversation "
            + "observations. Call exactly this tool."
        )
        prepared_messages = [dict(item) for item in messages]
        insert_at = 1 if prepared_messages and prepared_messages[0].get("role") == "system" else 0
        prepared_messages.insert(insert_at, {"role": "system", "content": prompt})
        return {"tool_name": name, "messages": prepared_messages,
                "tools": [dict(interface)], "tool_choice": "required"}

    def validate_arguments(self, tool_name: str,
                           arguments: str | Mapping[str, Any]) -> dict[str, Any]:
        if tool_name not in self.contracts:
            raise PlanExecutionError("argument request references an unknown tool")
        if isinstance(arguments, str):
            try:
                payload = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise PlanExecutionError("tool arguments are not valid JSON") from exc
        else:
            payload = dict(arguments)
        if not isinstance(payload, dict):
            raise PlanExecutionError("tool arguments must be a JSON object")
        params = self.contracts[tool_name].interface["function"]["parameters"]
        properties, required = params["properties"], set(params["required"])
        if not required.issubset(payload):
            raise PlanExecutionError("tool arguments are missing required observed inputs")
        if set(payload) - set(properties):
            raise PlanExecutionError("tool arguments contain fields outside the public schema")
        for key, value in payload.items():
            if not isinstance(value, str) or not value:
                raise PlanExecutionError("CostBench tool arguments must be non-empty strings")
            enum = properties[key].get("enum")
            if enum is not None and value not in enum:
                raise PlanExecutionError("tool argument is outside the public enum")
        return payload

    def record_tool_result(self, *, tool_name: str, success: bool,
                           observed_state_types: Iterable[str],
                           current_tool_interfaces: Iterable[Mapping[str, Any]]) -> str:
        if self.invalidated:
            raise PlanExecutionError("cannot record a result for an invalid certificate")
        if self.cursor >= len(self.plan) or self.plan[self.cursor] != tool_name:
            self.invalidate("executed_tool_did_not_match_committed_next_step")
            raise PlanExecutionError("executed tool differs from the committed next step")
        tools = tuple(dict(x) for x in current_tool_interfaces)
        digest = hashlib.sha256(canonical_json(list(tools)).encode()).hexdigest()
        if digest != self.certificate.tool_catalog_sha256:
            self.invalidate("tool_attributes_or_interfaces_changed")
            raise PlanExecutionError("tool catalogue changed during committed execution")
        observed = tuple(sorted(set(observed_state_types)))
        if not success:
            if observed != self.current_state:
                self.invalidate("failed_tool_changed_observed_state")
                raise PlanExecutionError("failed tool unexpectedly changed the state")
            self.invalidate("native_tool_execution_failed")
            return "REPLAN_REQUIRED"
        contract = self.contracts[tool_name]
        expected = tuple(sorted(set(self.current_state) | {contract.output_type}))
        if observed != expected:
            self.invalidate("native_observation_does_not_match_declared_output")
            raise PlanExecutionError("successful tool return and observed typed state disagree")
        self.cursor += 1
        self.current_state = observed
        remaining = self.plan[self.cursor:]
        if self.policy_input.goal_type in observed:
            if remaining:
                self.invalidate("committed_plan_continues_after_goal")
                raise PlanExecutionError("committed plan contains actions after goal completion")
            self.finished = True
            self.certificate = self._issue(0.0)
            return "GOAL_REACHED"
        check = check_submitted_path(observed, self.policy_input.goal_type, remaining, tools)
        if not check.valid or check.cost is None:
            self.invalidate("remaining_plan_invalid_after_native_observation")
            raise PlanExecutionError("remaining committed suffix is invalid: " + check.error_text)
        self.certificate = self._issue(check.cost)
        return "ADVANCED"

    def execution_record(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.policy_input.checkpoint_id,
            "committed_plan": list(self.plan),
            "cursor": self.cursor,
            "remaining_plan": list(self.plan[self.cursor:]),
            "current_state_types": list(self.current_state),
            "certificate_generation": self.generation,
            "certificate_sha256": (hashlib.sha256(
                canonical_json(self.certificate.__dict__).encode()).hexdigest()
                if self.certificate is not None else None),
            "invalidated": self.invalidated,
            "invalidation_reason": self.invalidation_reason,
            "finished": self.finished,
        }
