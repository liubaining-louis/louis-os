from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from atlas.provider_runtime import available, record_failure, reset_states, state_for, trim_prompt
from atlas.providers import ModelResponse, complete


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_states()

    def test_provider_enters_cooldown_after_repeated_failures(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_FAILURES_BEFORE_COOLDOWN": "2", "LLM_PROVIDER_COOLDOWN_SECONDS": "60"},
            clear=False,
        ):
            record_failure("groq", now=100.0)
            self.assertTrue(available("groq", now=100.0))
            record_failure("groq", now=101.0)
            self.assertFalse(available("groq", now=120.0))
            self.assertTrue(available("groq", now=162.0))

    def test_provider_call_budget_blocks_more_calls(self) -> None:
        with patch.dict(os.environ, {"GROQ_MAX_CALLS_PER_INSTANCE": "1"}, clear=False):
            state_for("groq").calls = 1
            self.assertFalse(available("groq", now=0.0))

    def test_prompt_is_trimmed_to_budget(self) -> None:
        with patch.dict(os.environ, {"LLM_MAX_PROMPT_CHARS": "2000"}, clear=False):
            result = trim_prompt("a" * 5000)
        self.assertLessEqual(len(result), 2050)
        self.assertIn("context truncated", result)

    def test_complete_skips_failed_primary_and_uses_secondary(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER_ORDER": "groq,vertex",
                "GROQ_API_KEY": "test",
                "GROQ_MODEL": "test-model",
                "VERTEX_PROJECT": "test-bot-499814",
                "VERTEX_LOCATION": "global",
                "VERTEX_MODEL": "gemini-2.5-flash",
                "LLM_FAILURES_BEFORE_COOLDOWN": "1",
            },
            clear=False,
        ), patch(
            "atlas.providers._complete_with_provider", side_effect=RuntimeError("rate limited")
        ), patch(
            "atlas.providers._complete_with_vertex",
            return_value=ModelResponse("vertex", "gemini-2.5-flash", "ok"),
        ):
            response = complete("analyse")

        self.assertEqual(response.provider, "vertex")
        self.assertFalse(available("groq"))


if __name__ == "__main__":
    unittest.main()
