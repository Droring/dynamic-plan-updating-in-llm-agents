"""Two-source complete-path generation with a hard three-call planning budget."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, inspect, json, time
from typing import Any, Callable
from .policy_input import PolicyInput, canonical_json

MAX_PLANNING_CALLS = 3
MAX_PLAN_TOKENS = 2048

@dataclass(frozen=True)
class CandidateProposal:
    source: str
    path: tuple[str, ...] | None
    call_index: int
    prompt_sha256: str
    response_sha256: str | None
    raw_response: str | None
    provider_tokens: int
    elapsed_seconds: float
    error: str | None

class CandidateGenerator:
    """Generate a repair candidate and an independent candidate using an injected client."""
    def __init__(self, completion: Callable[..., Any], *, max_calls: int = 3,
                 max_tokens: int = MAX_PLAN_TOKENS) -> None:
        if not 1 <= max_calls <= MAX_PLANNING_CALLS:
            raise ValueError("planning calls must be between one and three")
        self.completion = completion
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls_used = 0
        self.proposals: list[CandidateProposal] = []

    def _messages(self, policy_input: PolicyInput, source: str,
                  feedback: tuple[str, ...] = (),
                  failed_path: tuple[str, ...] | None = None) -> list[dict[str, str]]:
        include_incumbent = source in {"repair", "revision"}
        payload = policy_input.prompt_payload(include_incumbent)
        system = (
            "Produce one complete ordered tool path from the supplied current typed state "
            "to the goal using only the currently exposed tool catalogue. Return exactly "
            'one JSON object: {"plan":["Exact_Tool_Name", ...]}. Do not return arguments, '
            "a first action only, explanations, labels, or alternatives. Do not invent tools. "
            "The path must include every required dependency and reach the goal."
        )
        if source == "repair":
            system += (" Generate a local-repair candidate: preserve as much of the incumbent "
                       "remaining plan as is feasible, but return a complete current path.")
        elif source == "fresh":
            system += (" Generate independently from the current state and request. The "
                       "incumbent plan is intentionally not provided to this candidate.")
        elif source == "revision":
            system += (" Revise the failed submitted candidate into one complete path. Use "
                       "only the concrete validation feedback below; do not assume hidden facts.")
            payload["failed_candidate"] = list(failed_path or ())
            payload["validation_feedback"] = list(feedback)
        else:
            raise ValueError("unknown candidate source")
        return [{"role": "system", "content": system},
                {"role": "user", "content": canonical_json(payload)}]

    @staticmethod
    def _extract_text_and_tokens(response: Any) -> tuple[str, int]:
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        token_value = usage.get("total_tokens", 0) if isinstance(usage, dict) else getattr(usage, "total_tokens", 0)
        tokens = int(token_value or 0)
        if isinstance(response, str):
            return response, tokens
        if isinstance(response, dict):
            if "plan" in response:
                return json.dumps(response, ensure_ascii=False), tokens
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                return str((choices[0].get("message") or {}).get("content") or ""), tokens
        choices = getattr(response, "choices", None)
        if choices:
            return str(getattr(choices[0].message, "content", None) or ""), tokens
        raise ValueError("completion returned no JSON content")

    @staticmethod
    def _parse_path(raw: str) -> tuple[str, ...]:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("response_is_not_valid_json") from exc
        if not isinstance(value, dict) or set(value) != {"plan"}:
            raise ValueError("response_must_contain_only_the_plan_field")
        path = value["plan"]
        if not isinstance(path, list) or not path:
            raise ValueError("plan_must_be_a_nonempty_array")
        if any(not isinstance(name, str) or not name.strip() for name in path):
            raise ValueError("plan_entries_must_be_nonempty_tool_names")
        return tuple(name.strip() for name in path)

    async def _generate(self, policy_input: PolicyInput, source: str, *,
                        feedback: tuple[str, ...] = (),
                        failed_path: tuple[str, ...] | None = None) -> CandidateProposal:
        if self.calls_used >= self.max_calls:
            raise RuntimeError("planning_call_budget_exhausted")
        messages = self._messages(policy_input, source, feedback, failed_path)
        prompt_sha = hashlib.sha256(canonical_json(messages).encode()).hexdigest()
        self.calls_used += 1
        call_index = self.calls_used
        started = time.perf_counter()
        raw = None
        response_sha = None
        tokens = 0
        path = None
        error = None
        try:
            response = self.completion(messages=messages,
                response_format={"type": "json_object"}, max_tokens=self.max_tokens)
            if inspect.isawaitable(response):
                response = await response
        except Exception as exc:
            error = "completion_error:" + (str(exc) or type(exc).__name__)
        else:
            try:
                raw, tokens = self._extract_text_and_tokens(response)
                response_sha = hashlib.sha256(raw.encode()).hexdigest()
                path = self._parse_path(raw)
            except Exception as exc:
                error = "candidate_format_error:" + (str(exc) or type(exc).__name__)
        proposal = CandidateProposal(source, path, call_index, prompt_sha, response_sha,
            raw, tokens, round(time.perf_counter()-started, 7), error)
        self.proposals.append(proposal)
        return proposal

    async def generate_repair(self, policy_input: PolicyInput) -> CandidateProposal:
        return await self._generate(policy_input, "repair")

    async def generate_fresh(self, policy_input: PolicyInput) -> CandidateProposal:
        return await self._generate(policy_input, "fresh")

    async def generate_revision(self, policy_input: PolicyInput,
                                failed_path: tuple[str, ...] | None,
                                feedback: tuple[str, ...]) -> CandidateProposal:
        if not feedback:
            raise ValueError("revision requires concrete validation feedback")
        return await self._generate(policy_input, "revision",
                                    feedback=feedback, failed_path=failed_path)
