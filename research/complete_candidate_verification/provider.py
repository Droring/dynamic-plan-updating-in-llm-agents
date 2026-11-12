"""Budgeted, no-retry DeepSeek calls with durable pre-request audit records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import BudgetExceeded, ProviderOutcomeUnknown
from .scoring_logging import append_jsonl_durable

DEFAULT_MODEL = "deepseek-flash"
RESERVATION_BUFFER = 512


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _total_tokens(response: Any) -> int | None:
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    value = usage.get("total_tokens") if isinstance(usage, dict) else getattr(usage, "total_tokens", None)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class BudgetedDeepSeekProvider:
    """One sequential ledger shared by all planning and argument calls."""

    def __init__(self, client: Any, *, audit_path: str | Path, token_cap: int,
                 model: str = DEFAULT_MODEL, reservation_buffer: int = RESERVATION_BUFFER):
        if token_cap <= 0 or reservation_buffer < 0:
            raise ValueError("invalid provider budget configuration")
        self.client = client
        self.audit_path = Path(audit_path)
        self.token_cap = token_cap
        self.model = model
        self.reservation_buffer = reservation_buffer
        self.charged_tokens = 0
        self.reserved_tokens = 0
        self.calls = 0
        self.context: dict[str, str] = {}

    def set_context(self, **values: str) -> None:
        self.context = {key: str(value) for key, value in values.items()}

    def _reservation(self, *, messages: Any, max_tokens: int, tools: Any = None,
                     tool_choice: Any = None, response_format: Any = None) -> int:
        payload = {
            "model": self.model, "messages": messages, "tools": tools or [],
            "tool_choice": tool_choice, "response_format": response_format,
            "temperature": 0, "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        }
        return len(_canonical(payload).encode("utf-8")) + max_tokens + self.reservation_buffer

    async def _call(self, kind: str, *, messages: Any, max_tokens: int,
                    tools: Any = None, tool_choice: Any = None,
                    response_format: Any = None) -> Any:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        reserve = self._reservation(messages=messages, max_tokens=max_tokens,
                                    tools=tools, tool_choice=tool_choice,
                                    response_format=response_format)
        prompt_sha = hashlib.sha256(_canonical(messages).encode("utf-8")).hexdigest()
        if self.charged_tokens + reserve > self.token_cap:
            append_jsonl_durable(self.audit_path, {
                "event": "request_blocked_before_send", "call_index": self.calls + 1,
                "kind": kind, "prompt_sha256": prompt_sha,
                "reservation_tokens": reserve, "charged_tokens": self.charged_tokens,
                "token_cap": self.token_cap, **self.context,
            })
            raise BudgetExceeded(
                f"request reservation {reserve} exceeds remaining token budget "
                f"({self.charged_tokens}/{self.token_cap} charged)"
            )

        self.calls += 1
        call_index = self.calls
        self.reserved_tokens += reserve
        append_jsonl_durable(self.audit_path, {
            "event": "request_started", "call_index": call_index, "kind": kind,
            "model": self.model, "prompt_sha256": prompt_sha,
            "reservation_tokens": reserve, "charged_tokens_before": self.charged_tokens,
            "token_cap": self.token_cap, **self.context,
        })

        kwargs = {
            "model": self.model, "messages": messages, "temperature": 0,
            "max_tokens": max_tokens,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if tools is not None:
            kwargs.update(tools=tools, tool_choice=tool_choice, parallel_tool_calls=False)

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            append_jsonl_durable(self.audit_path, {
                "event": "outcome_unknown", "call_index": call_index, "kind": kind,
                "prompt_sha256": prompt_sha, "error_type": type(exc).__name__,
                "error": str(exc)[:1000], **self.context,
            })
            raise ProviderOutcomeUnknown(
                f"{kind} request {call_index} outcome is unknown: {type(exc).__name__}: {exc}"
            ) from exc

        used = _total_tokens(response)
        if used is None:
            append_jsonl_durable(self.audit_path, {
                "event": "usage_missing_outcome_unknown", "call_index": call_index,
                "kind": kind, "prompt_sha256": prompt_sha, **self.context,
            })
            raise ProviderOutcomeUnknown(
                f"{kind} request {call_index} returned without reliable total_tokens usage"
            )
        self.charged_tokens += used
        append_jsonl_durable(self.audit_path, {
            "event": "response_received", "call_index": call_index, "kind": kind,
            "prompt_sha256": prompt_sha, "used_tokens": used,
            "charged_tokens_after": self.charged_tokens,
            "reservation_tokens": reserve, **self.context,
        })
        if self.charged_tokens > self.token_cap:
            raise BudgetExceeded(
                f"actual provider usage {self.charged_tokens} exceeded hard cap {self.token_cap}"
            )
        return response

    def candidate_completion(self):
        async def complete(*, messages, response_format, max_tokens):
            return await self._call("candidate_generation", messages=messages,
                                    response_format=response_format, max_tokens=max_tokens)
        return complete

    def argument_completion(self):
        async def complete(*, messages, tools, tool_choice, max_tokens):
            return await self._call("argument_generation", messages=messages, tools=tools,
                                    tool_choice=tool_choice, max_tokens=max_tokens)
        return complete

    def snapshot(self) -> dict[str, int]:
        return {
            "provider_calls": self.calls, "charged_tokens": self.charged_tokens,
            "reserved_tokens": self.reserved_tokens, "token_cap": self.token_cap,
            "remaining_tokens": max(0, self.token_cap - self.charged_tokens),
        }
