from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from .errors import BudgetExceeded, ProviderOutcomeUnknown
from .provider import BudgetedDeepSeekProvider


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_blocks_before_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeCompletions(response={"usage": {"total_tokens": 1}})
            provider = BudgetedDeepSeekProvider(
                SimpleNamespace(chat=SimpleNamespace(completions=api)),
                audit_path=Path(tmp) / "events.jsonl", token_cap=10,
            )
            with self.assertRaises(BudgetExceeded):
                await provider.candidate_completion()(
                    messages=[{"role": "user", "content": "a long prompt"}],
                    response_format={"type": "json_object"}, max_tokens=2048,
                )
            self.assertEqual(api.calls, [])
            events = [json.loads(x) for x in (Path(tmp) / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[0]["event"], "request_blocked_before_send")

    async def test_success_is_charged_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeCompletions(response={
                "usage": {"total_tokens": 17}, "choices": [{"message": {"content": "ok"}}]
            })
            provider = BudgetedDeepSeekProvider(
                SimpleNamespace(chat=SimpleNamespace(completions=api)),
                audit_path=Path(tmp) / "events.jsonl", token_cap=10000,
            )
            provider.set_context(trial_id="trial-1", method="repair_plus_fresh")
            await provider.candidate_completion()(
                messages=[{"role": "user", "content": "plan"}],
                response_format={"type": "json_object"}, max_tokens=128,
            )
            self.assertEqual(provider.charged_tokens, 17)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(api.calls[0]["model"], "deepseek-flash")
            self.assertEqual(api.calls[0]["temperature"], 0)
            self.assertEqual(api.calls[0]["extra_body"], {"thinking": {"type": "disabled"}})
            events = [json.loads(x) for x in (Path(tmp) / "events.jsonl").read_text().splitlines()]
            self.assertEqual([x["event"] for x in events], ["request_started", "response_received"])
            self.assertEqual(events[-1]["used_tokens"], 17)

    async def test_provider_error_is_unknown_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeCompletions(error=TimeoutError("read timeout"))
            provider = BudgetedDeepSeekProvider(
                SimpleNamespace(chat=SimpleNamespace(completions=api)),
                audit_path=Path(tmp) / "events.jsonl", token_cap=10000,
            )
            with self.assertRaisesRegex(ProviderOutcomeUnknown, "outcome is unknown"):
                await provider.argument_completion()(
                    messages=[{"role": "user", "content": "args"}],
                    tools=[{"type": "function", "function": {"name": "A"}}],
                    tool_choice="required", max_tokens=128,
                )
            self.assertEqual(len(api.calls), 1)
            events = [json.loads(x) for x in (Path(tmp) / "events.jsonl").read_text().splitlines()]
            self.assertEqual([x["event"] for x in events], ["request_started", "outcome_unknown"])

    async def test_missing_usage_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeCompletions(response={"choices": [{"message": {"content": "ok"}}]})
            provider = BudgetedDeepSeekProvider(
                SimpleNamespace(chat=SimpleNamespace(completions=api)),
                audit_path=Path(tmp) / "events.jsonl", token_cap=10000,
            )
            with self.assertRaisesRegex(ProviderOutcomeUnknown, "without reliable"):
                await provider.candidate_completion()(
                    messages=[{"role": "user", "content": "plan"}],
                    response_format={"type": "json_object"}, max_tokens=128,
                )
            events = [json.loads(x) for x in (Path(tmp) / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "usage_missing_outcome_unknown")


if __name__ == "__main__":
    unittest.main()
