"""Bounded type-contract substitutions around already proposed complete plans.

This module does not plan from the initial state to the goal. It only searches a
small, fixed neighborhood around contiguous segments of supplied complete paths.
Every resulting full path is passed to the submitted-path-only checker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .policy_input import PolicyInput, parse_public_tool_interfaces
from .submitted_plan_checker import EPSILON, check_policy_path


@dataclass(frozen=True)
class LocalSubstitution:
    source_path: tuple[str, ...]
    start_index: int
    end_index: int
    replacement_path: tuple[str, ...]
    candidate_path: tuple[str, ...]
    source_value: float
    replaced_segment_value: float
    replacement_value: float
    candidate_value: float

    def to_record(self) -> dict:
        return {
            "source_path": list(self.source_path),
            "start_index": self.start_index,
            "end_index_exclusive": self.end_index,
            "replacement_path": list(self.replacement_path),
            "candidate_path": list(self.candidate_path),
            "source_value": self.source_value,
            "replaced_segment_value": self.replaced_segment_value,
            "replacement_value": self.replacement_value,
            "candidate_value": self.candidate_value,
        }


def generate_local_substitutions(
    policy_input: PolicyInput,
    base_paths: Iterable[Sequence[str]],
    *,
    max_segment_length: int = 4,
    max_replacement_length: int = 2,
) -> tuple[LocalSubstitution, ...]:
    """Generate strict-improvement paths by bounded contract-equivalent replacement.

    A contiguous segment is anchored by the output type of its final tool. The
    replacement sequence must be executable from the state at the segment boundary
    and must produce that output type. The complete spliced path is then validated
    by check_policy_path; missing intermediate types or invalid suffixes are rejected.

    Search is bounded to segments of at most four tools and replacements of at most
    two tools by default. It never enumerates arbitrary paths from the checkpoint.
    """
    if max_segment_length <= 0 or max_replacement_length <= 0:
        raise ValueError("substitution bounds must be positive")

    contracts = parse_public_tool_interfaces(policy_input.tool_interfaces)
    ordered = tuple(contracts[name] for name in sorted(contracts))
    records: dict[tuple[str, ...], LocalSubstitution] = {}

    unique_bases = []
    seen_bases = set()
    for raw_path in base_paths:
        path = tuple(raw_path)
        if path and path not in seen_bases:
            seen_bases.add(path)
            unique_bases.append(path)

    for base in unique_bases:
        base_check = check_policy_path(policy_input, base)
        if not base_check.valid or base_check.cost is None:
            continue

        states = [set(policy_input.current_state_types)]
        prefix_values = [0.0]
        for name in base:
            contract = contracts[name]
            next_state = set(states[-1])
            next_state.add(contract.output_type)
            states.append(next_state)
            prefix_values.append(prefix_values[-1] + contract.cost)

        for start in range(len(base)):
            last_end = min(len(base), start + max_segment_length)
            for end in range(start + 1, last_end + 1):
                boundary_type = contracts[base[end - 1]].output_type
                old_segment_value = prefix_values[end] - prefix_values[start]
                start_state = states[start]

                # Each frontier item is a replacement prefix and its resulting state.
                frontier = [((), set(start_state), 0.0)]
                for depth in range(1, max_replacement_length + 1):
                    next_frontier = []
                    for replacement, current_state, replacement_value in frontier:
                        for contract in ordered:
                            if contract.name in replacement:
                                continue
                            if contract.output_type in current_state:
                                continue
                            if not set(contract.required_inputs).issubset(current_state):
                                continue

                            next_replacement = replacement + (contract.name,)
                            next_state = set(current_state)
                            next_state.add(contract.output_type)
                            next_value = replacement_value + contract.cost

                            if boundary_type in next_state and next_value < old_segment_value - EPSILON:
                                candidate = base[:start] + next_replacement + base[end:]
                                if candidate != base:
                                    candidate_check = check_policy_path(policy_input, candidate)
                                    if (candidate_check.valid and candidate_check.cost is not None
                                            and candidate_check.cost < base_check.cost - EPSILON):
                                        record = LocalSubstitution(
                                            source_path=base,
                                            start_index=start,
                                            end_index=end,
                                            replacement_path=next_replacement,
                                            candidate_path=candidate,
                                            source_value=base_check.cost,
                                            replaced_segment_value=round(old_segment_value, 9),
                                            replacement_value=round(next_value, 9),
                                            candidate_value=candidate_check.cost,
                                        )
                                        previous = records.get(candidate)
                                        order = (record.candidate_value, len(record.candidate_path),
                                                 record.candidate_path, len(record.replacement_path),
                                                 record.replacement_path, record.source_path,
                                                 record.start_index, record.end_index)
                                        if previous is None:
                                            records[candidate] = record
                                        else:
                                            old_order = (previous.candidate_value,
                                                len(previous.candidate_path), previous.candidate_path,
                                                len(previous.replacement_path), previous.replacement_path,
                                                previous.source_path, previous.start_index,
                                                previous.end_index)
                                            if order < old_order:
                                                records[candidate] = record

                            if depth < max_replacement_length and policy_input.goal_type not in next_state:
                                next_frontier.append((next_replacement, next_state, next_value))
                    frontier = next_frontier

    return tuple(sorted(records.values(), key=lambda item: (
        item.candidate_value, len(item.candidate_path), item.candidate_path,
        item.source_path, item.start_index, item.end_index,
    )))
