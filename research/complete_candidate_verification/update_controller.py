"""Orchestrate candidate generation and deterministic strict plan selection."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Sequence
from .candidate_generator import CandidateGenerator, CandidateProposal
from .policy_input import PolicyInput
from .submitted_plan_checker import PathCheck, PlanSelection, check_policy_path, select_strictly_better_plan

@dataclass(frozen=True)
class UpdateDecision:
    action: str
    selected_plan: tuple[str, ...] | None
    reason: str
    incumbent_check: PathCheck
    candidate_checks: tuple[PathCheck, ...]
    proposals: tuple[CandidateProposal, ...]
    planning_calls: int
    provider_tokens: int

def _check_proposals(policy_input: PolicyInput,
                     proposals: Sequence[CandidateProposal]) -> tuple[PathCheck, ...]:
    checks = []
    for proposal in proposals:
        if proposal.path is None:
            checks.append(PathCheck((), False, False, False, None,
                policy_input.current_state_types, (proposal.error or "candidate_generation_failed",)))
        else:
            checks.append(check_policy_path(policy_input, proposal.path))
    return tuple(checks)

def _decision(selection: PlanSelection, incumbent: PathCheck,
              checks: tuple[PathCheck, ...], proposals: Sequence[CandidateProposal],
              generator: CandidateGenerator) -> UpdateDecision:
    return UpdateDecision(selection.action, selection.selected_plan, selection.reason,
        incumbent, checks, tuple(proposals), generator.calls_used,
        sum(x.provider_tokens for x in proposals))

async def run_update(policy_input: PolicyInput,
                     completion: Callable[..., Any]) -> UpdateDecision:
    """Two initial candidates; one feedback revision only for concrete invalidity."""
    generator = CandidateGenerator(completion, max_calls=3)
    incumbent = check_policy_path(policy_input, policy_input.old_remaining_plan)
    proposals = [await generator.generate_repair(policy_input),
                 await generator.generate_fresh(policy_input)]
    checks = _check_proposals(policy_input, proposals)
    paths = [p.path for p in proposals if p.path is not None]
    selection = select_strictly_better_plan(policy_input, paths)
    if selection.action == "SWITCH":
        return _decision(selection, incumbent, checks, proposals, generator)

    # A valid tie/loss is not a reason to spend a third call.
    invalid_indices = [i for i, check in enumerate(checks)
                       if not check.valid and proposals[i].path is not None]
    format_indices = [i for i, proposal in enumerate(proposals)
                      if proposal.error and proposal.error.startswith("candidate_format_error:")]
    repairable = sorted(set(invalid_indices + format_indices))
    if repairable and generator.calls_used < generator.max_calls:
        index = repairable[0]
        feedback = checks[index].errors
        if not feedback:
            feedback = (proposals[index].error or "candidate_format_error",)
        revision = await generator.generate_revision(
            policy_input, proposals[index].path, tuple(feedback))
        proposals.append(revision)
        checks = _check_proposals(policy_input, proposals)
        paths = [p.path for p in proposals if p.path is not None]
        selection = select_strictly_better_plan(policy_input, paths)
    return _decision(selection, incumbent, checks, proposals, generator)
