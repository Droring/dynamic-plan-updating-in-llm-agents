"""Orchestrate fresh candidate generation and deterministic strict plan selection."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Sequence
from .candidate_generator import CandidateGenerator, CandidateProposal
from .policy_input import PolicyInput
from .submitted_plan_checker import PathCheck, PlanSelection, check_policy_path, select_strictly_better_plan
from .local_plan_substitution import LocalSubstitution, generate_local_substitutions

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
    candidate_strategy: str
    local_substitutions: tuple[LocalSubstitution, ...] = ()

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
              generator: CandidateGenerator,
              candidate_strategy: str,
              local_substitutions: Sequence[LocalSubstitution] = ()) -> UpdateDecision:
    return UpdateDecision(selection.action, selection.selected_plan, selection.reason,
        incumbent, checks, tuple(proposals), generator.calls_used,
        sum(x.provider_tokens for x in proposals), candidate_strategy,
        tuple(local_substitutions))

async def run_update(policy_input: PolicyInput,
                     completion: Callable[..., Any],
                     candidate_strategy: str = "fresh_only") -> UpdateDecision:
    """Run the one-candidate policy or an explicitly requested frozen-screen replay.

    The current simplified policy makes exactly one Fresh planning request. The two
    historical strategies are retained only to reproduce the completed development
    screen; they are not used by the current method or its default execution path.
    """
    incumbent = check_policy_path(policy_input, policy_input.old_remaining_plan)

    if candidate_strategy in {"fresh_only", "fresh_with_local_substitution"}:
        generator = CandidateGenerator(completion, max_calls=1)
        proposals = [await generator.generate_fresh(policy_input)]
        if candidate_strategy == "fresh_only":
            checks = _check_proposals(policy_input, proposals)
            paths = [proposal.path for proposal in proposals if proposal.path is not None]
            selection = select_strictly_better_plan(policy_input, paths)
            return _decision(selection, incumbent, checks, proposals, generator, candidate_strategy)

        # The local operator is anchored only to the incumbent and one Fresh proposal.
        # It does not search arbitrary paths from the checkpoint.
        base_paths = []
        if incumbent.valid:
            base_paths.append(incumbent.path)
        if proposals[0].path is not None:
            base_paths.append(proposals[0].path)
        substitutions = generate_local_substitutions(policy_input, base_paths)
        paths = [proposal.path for proposal in proposals if proposal.path is not None]
        paths.extend(item.candidate_path for item in substitutions)
        selection = select_strictly_better_plan(policy_input, paths)
        return _decision(selection, incumbent, selection.candidate_checks,
                         proposals, generator, candidate_strategy, substitutions)

    # Frozen historical development-screen replay. Do not use these strategies for
    # new method runs: the two Fresh prompts are identical, and Repair added no
    # unique strict-better SWITCH coverage in the completed development cohort.
    if candidate_strategy not in {"repair_plus_fresh", "fresh_plus_fresh"}:
        raise ValueError("unknown candidate strategy")

    generator = CandidateGenerator(completion, max_calls=3)
    if candidate_strategy == "repair_plus_fresh":
        proposals = [await generator.generate_repair(policy_input),
                     await generator.generate_fresh(policy_input)]
    else:
        proposals = [await generator.generate_fresh(policy_input),
                     await generator.generate_fresh(policy_input)]
    checks = _check_proposals(policy_input, proposals)
    paths = [proposal.path for proposal in proposals if proposal.path is not None]
    selection = select_strictly_better_plan(policy_input, paths)
    if selection.action == "SWITCH":
        return _decision(selection, incumbent, checks, proposals, generator, candidate_strategy)

    # Preserve the frozen historical revision rule only for exact replay.
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
            policy_input, proposals[index].path, tuple(feedback),
            include_incumbent=(candidate_strategy == "repair_plus_fresh"))
        proposals.append(revision)
        checks = _check_proposals(policy_input, proposals)
        paths = [proposal.path for proposal in proposals if proposal.path is not None]
        selection = select_strictly_better_plan(policy_input, paths)
    return _decision(selection, incumbent, checks, proposals, generator, candidate_strategy)
