"""Whitelisted, observation-grounded policy inputs."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, math, re
from typing import Any, Iterable, Mapping, Sequence

_COST = re.compile(r"\bThis tool has a cost of ([0-9]+(?:\.[0-9]+)?) units\.")
_OUTPUT = re.compile(r"\bThe output type of this tool is ([A-Za-z][A-Za-z0-9_]*)\.")
_FORBIDDEN_KEYS = {
    "condition", "environment_condition", "oracle", "oracle_cost", "oracle_value",
    "regret", "native_optimal_path", "native_regret_audit", "gold_label",
    "correct_answer", "groundtruth", "ground_truth", "reference_path",
    "reference_optimal", "optimal_path", "answer_key", "solver", "solver_result",
}

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def reject_evaluation_fields(value: Any, path: str = "input") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in _FORBIDDEN_KEYS:
                raise ValueError(f"evaluation-only field is forbidden in policy input: {path}.{key}")
            reject_evaluation_fields(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_evaluation_fields(child, f"{path}[{index}]")

@dataclass(frozen=True)
class ToolContract:
    name: str
    required_inputs: tuple[str, ...]
    output_type: str
    cost: float
    interface: Mapping[str, Any]

    def public_record(self) -> dict[str, Any]:
        return {"name": self.name, "required_inputs": list(self.required_inputs),
                "output_type": self.output_type, "cost": self.cost,
                "interface": dict(self.interface)}

def parse_public_tool_interfaces(interfaces: Iterable[Mapping[str, Any]]) -> dict[str, ToolContract]:
    result: dict[str, ToolContract] = {}
    for interface in interfaces:
        reject_evaluation_fields(interface, "tool_interface")
        if interface.get("type") != "function":
            raise ValueError("only function tool interfaces are supported")
        function = interface.get("function")
        if not isinstance(function, Mapping):
            raise ValueError("tool interface has no function object")
        name, description = function.get("name"), function.get("description", "")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("tool name is invalid or duplicated")
        if not isinstance(description, str) or not isinstance(parameters, Mapping):
            raise ValueError(f"tool description or parameters are invalid: {name}")
        properties, required = parameters.get("properties"), parameters.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            raise ValueError(f"tool parameter schema is invalid: {name}")
        if len(required) != len(set(required)) or any(not isinstance(x, str) for x in required):
            raise ValueError(f"tool required-input list is invalid: {name}")
        if not set(required).issubset(properties):
            raise ValueError(f"tool required inputs are absent from properties: {name}")
        cm, om = _COST.search(description), _OUTPUT.search(description)
        if cm is None or om is None:
            raise ValueError(f"public description lacks cost/output metadata: {name}")
        cost = float(cm.group(1))
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError(f"tool cost must be positive and finite: {name}")
        result[name] = ToolContract(name, tuple(required), om.group(1), cost, dict(interface))
    if not result:
        raise ValueError("the current public tool catalogue is empty")
    return result

def reconstruct_observed_state(initial_state_types: Iterable[str],
                               executed_trace: Sequence[Mapping[str, Any]],
                               tool_interfaces: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Add only output types from successful native calls; never advance on failure."""
    contracts = parse_public_tool_interfaces(tool_interfaces)
    state = set(initial_state_types)
    if any(not isinstance(x, str) or not x for x in state):
        raise ValueError("initial state types must be non-empty strings")
    failed = False
    for index, item in enumerate(executed_trace):
        if failed:
            raise ValueError("trace contains actions after a failed native tool call")
        name = item.get("tool_name")
        if name not in contracts:
            raise ValueError(f"trace references a tool outside the observed catalogue: {name}")
        contract = contracts[name]
        success = item.get("success")
        if not isinstance(success, bool):
            raise ValueError(f"trace success flag is missing at step {index}")
        if not set(contract.required_inputs).issubset(state):
            raise ValueError(f"trace is not state-feasible at step {index}: {name}")
        if success:
            observed_type = item.get("observed_output_type", contract.output_type)
            if observed_type != contract.output_type:
                raise ValueError(f"observed output type disagrees with public contract: {name}")
            state.add(observed_type)
        else:
            failed = True
    return tuple(sorted(state))

@dataclass(frozen=True)
class PolicyInput:
    task: str
    user_request: str
    goal_type: str
    current_state_types: tuple[str, ...]
    old_remaining_plan: tuple[str, ...]
    tool_interfaces: tuple[Mapping[str, Any], ...]
    checkpoint_id: str
    observation_history: tuple[Mapping[str, Any], ...] = ()

    @property
    def tool_catalog_sha256(self) -> str:
        return sha256_json(list(self.tool_interfaces))

    @property
    def state_sha256(self) -> str:
        return sha256_json(list(self.current_state_types))

    def prompt_payload(self, include_incumbent: bool) -> dict[str, Any]:
        payload = {"task": self.task, "user_request": self.user_request,
                   "goal_type": self.goal_type,
                   "current_state_types": list(self.current_state_types),
                   "current_tools": list(self.tool_interfaces),
                   "observation_history": [dict(item) for item in self.observation_history]}
        if include_incumbent:
            payload["incumbent_remaining_plan"] = list(self.old_remaining_plan)
        reject_evaluation_fields(payload)
        return payload

def build_policy_input(*, task: str, user_request: str, goal_type: str,
                       observed_state_types: Iterable[str],
                       old_remaining_plan: Sequence[str],
                       current_tool_interfaces: Sequence[Mapping[str, Any]],
                       checkpoint_id: str,
                       observation_history: Sequence[Mapping[str, Any]] = (),
                       source_record: Mapping[str, Any] | None = None) -> PolicyInput:
    if source_record is not None:
        reject_evaluation_fields(source_record, "source_record")
    for name, value in (("task", task), ("user_request", user_request),
                        ("goal_type", goal_type), ("checkpoint_id", checkpoint_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    state = tuple(sorted(set(observed_state_types)))
    if any(not isinstance(x, str) or not x for x in state):
        raise ValueError("observed state types must be non-empty strings")
    if goal_type in state:
        raise ValueError("checkpoint is already terminal; no replanning decision is required")
    old = tuple(old_remaining_plan)
    if not old or any(not isinstance(x, str) or not x for x in old):
        raise ValueError("a complete non-empty incumbent remaining plan is required")
    interfaces = tuple(json.loads(canonical_json(x)) for x in current_tool_interfaces)
    contracts = parse_public_tool_interfaces(interfaces)
    history: list[dict[str, Any]] = []
    for index, raw_item in enumerate(observation_history):
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"observation history entry {index} must be an object")
        reject_evaluation_fields(raw_item, f"observation_history[{index}]")
        required_keys = {"tool_name", "arguments", "observation", "output_type", "output_id"}
        if set(raw_item) != required_keys:
            raise ValueError(f"observation history entry {index} has an invalid schema")
        name = raw_item["tool_name"]
        if not isinstance(name, str) or name not in contracts:
            raise ValueError(f"observation history references an unavailable tool at {index}")
        contract = contracts[name]
        arguments = raw_item["arguments"]
        if not isinstance(arguments, Mapping):
            raise ValueError(f"observation history arguments must be an object at {index}")
        properties = contract.interface["function"]["parameters"]["properties"]
        required_inputs = set(contract.required_inputs)
        if not required_inputs.issubset(arguments) or set(arguments) - set(properties):
            raise ValueError(f"observation history arguments violate the public schema at {index}")
        if any(not isinstance(value, str) or not value for value in arguments.values()):
            raise ValueError(f"observation history arguments must be non-empty strings at {index}")
        if raw_item["output_type"] != contract.output_type:
            raise ValueError(f"observation history output type disagrees with the tool contract at {index}")
        if raw_item["output_type"] not in state:
            raise ValueError(f"observation history output type is absent from observed state at {index}")
        if not isinstance(raw_item["observation"], str) or not raw_item["observation"].strip():
            raise ValueError(f"observation history must contain the exact native observation at {index}")
        if not isinstance(raw_item["output_id"], str) or not raw_item["output_id"].strip():
            raise ValueError(f"observation history must contain the native output identifier at {index}")
        history.append(json.loads(canonical_json(raw_item)))
    return PolicyInput(task.strip(), user_request.strip(), goal_type.strip(),
                       state, old, interfaces, checkpoint_id, tuple(history))

def build_policy_input_from_trace(*, task: str, user_request: str, goal_type: str,
                                  initial_state_types: Iterable[str],
                                  successful_tool_trace: Sequence[Mapping[str, Any]],
                                  old_remaining_plan: Sequence[str],
                                  current_tool_interfaces: Sequence[Mapping[str, Any]],
                                  checkpoint_id: str) -> PolicyInput:
    state = reconstruct_observed_state(initial_state_types, successful_tool_trace,
                                        current_tool_interfaces)
    return build_policy_input(task=task, user_request=user_request, goal_type=goal_type,
        observed_state_types=state, old_remaining_plan=old_remaining_plan,
        current_tool_interfaces=current_tool_interfaces, checkpoint_id=checkpoint_id)
