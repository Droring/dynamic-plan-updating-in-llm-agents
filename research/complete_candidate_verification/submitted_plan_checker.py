"""Submitted-path-only validation; no search, completion, or oracle access."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence
from .policy_input import PolicyInput, parse_public_tool_interfaces

EPSILON = 1e-6

@dataclass(frozen=True)
class PathCheck:
    path: tuple[str, ...]
    valid: bool
    feasible: bool
    complete: bool
    cost: float | None
    terminal_state: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def error_text(self) -> str:
        return "; ".join(self.errors)

@dataclass(frozen=True)
class PlanSelection:
    action: str
    selected_plan: tuple[str, ...] | None
    selected_check: PathCheck | None
    incumbent_check: PathCheck
    candidate_checks: tuple[PathCheck, ...]
    reason: str

def check_submitted_path(current_state_types: Iterable[str], goal_type: str,
                         submitted_path: Sequence[str],
                         tool_interfaces: Iterable[Mapping[str, Any]]) -> PathCheck:
    """Check exactly the submitted sequence; never insert, expand, or search actions."""
    path = tuple(submitted_path)
    contracts = parse_public_tool_interfaces(tool_interfaces)
    state = set(current_state_types)
    errors: list[str] = []
    total = 0.0
    if any(not isinstance(name, str) or not name for name in path):
        return PathCheck(path, False, False, False, None, tuple(sorted(state)),
                         ("path_contains_invalid_tool_name",))
    if goal_type in state:
        if path:
            errors.append("actions_remain_after_goal_already_available")
        return PathCheck(path, not errors, not errors, not errors,
                         0.0 if not errors else None, tuple(sorted(state)), tuple(errors))
    if not path:
        return PathCheck(path, False, False, False, None, tuple(sorted(state)),
                         ("empty_path_does_not_reach_goal",))
    for index, name in enumerate(path):
        contract = contracts.get(name)
        if contract is None:
            errors.append(f"step_{index + 1}:tool_not_currently_available:{name}")
            break
        missing = sorted(set(contract.required_inputs) - state)
        if missing:
            errors.append(f"step_{index + 1}:missing_preconditions:{name}:{','.join(missing)}")
            break
        if contract.output_type in state:
            errors.append(f"step_{index + 1}:no_new_state_effect:{name}:{contract.output_type}")
            break
        total += contract.cost
        state.add(contract.output_type)
        if goal_type in state and index != len(path) - 1:
            errors.append("path_contains_actions_after_goal")
            break
    feasible = not errors
    complete = feasible and goal_type in state
    if feasible and not complete:
        errors.append("submitted_path_does_not_reach_goal")
    valid = feasible and complete and math.isfinite(total)
    return PathCheck(path, valid, feasible, complete,
                     round(total, 9) if valid else None,
                     tuple(sorted(state)), tuple(errors))

def check_policy_path(policy_input: PolicyInput, path: Sequence[str]) -> PathCheck:
    return check_submitted_path(policy_input.current_state_types, policy_input.goal_type,
                                path, policy_input.tool_interfaces)

def select_strictly_better_plan(policy_input: PolicyInput,
                                candidate_paths: Sequence[Sequence[str]]) -> PlanSelection:
    """Retain a feasible incumbent on ties; switch only to a strictly better path."""
    old = check_policy_path(policy_input, policy_input.old_remaining_plan)
    checks = tuple(check_policy_path(policy_input, path) for path in candidate_paths)
    valid_candidates = [x for x in checks if x.valid]
    if old.valid:
        better = [x for x in valid_candidates if x.cost is not None and old.cost is not None
                  and x.cost < old.cost - EPSILON]
        if not better:
            return PlanSelection("RETAIN", old.path, old, old, checks,
                                 "no_feasible_candidate_is_strictly_better_than_incumbent")
        chosen = min(better, key=lambda x: (x.cost, len(x.path), x.path))
        return PlanSelection("SWITCH", chosen.path, chosen, old, checks,
                             "selected_feasible_candidate_has_strictly_lower_current_path_value")
    if not valid_candidates:
        return PlanSelection("STOP", None, None, old, checks,
            "incumbent_is_not_feasible_and_no_submitted_candidate_is_complete_and_feasible")
    chosen = min(valid_candidates, key=lambda x: (x.cost, len(x.path), x.path))
    return PlanSelection("SWITCH", chosen.path, chosen, old, checks,
                         "incumbent_is_invalid_and_a_complete_feasible_candidate_was_submitted")
