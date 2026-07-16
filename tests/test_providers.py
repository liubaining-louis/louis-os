import os
import unittest
from unittest.mock import patch

from atlas.providers import (
    ModelResponse,
    ProviderConfig,
    _provider_config,
    _provider_order,
    _request_headers,
    complete,
    complete_with,
)


class ProviderHeaderTests(unittest.TestCase):
    def test_explicit_user_agent_and_accept_headers(self):
        headers = _request_headers("secret-value", "groq")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertTrue(headers["User-Agent"].startswith("LouisOS/"))
        self.assertEqual(headers["Authorization"], "Bearer secret-value")
        self.assertNotIn("secret-value", headers["User-Agent"])

    def test_openrouter_metadata_headers(self):
        headers = _request_headers("secret-value", "openrouter")
        self.assertIn("HTTP-Referer", headers)
        self.assertEqual(headers["X-Title"], "Louis OS")

    def test_other_provider_does_not_receive_openrouter_headers(self):
        headers = _request_headers("secret-value", "groq")
        self.assertNotIn("HTTP-Referer", headers)
        self.assertNotIn("X-Title", headers)


class ProviderRoutingTests(unittest.TestCase):
    def test_targeted_provider_call_does_not_fallback(self):
        env = {"GROQ_API_KEY": "test-key"}
        expected = ModelResponse("groq", "llama-3.3-70b-versatile", "ok")
        with patch.dict(os.environ, env, clear=True), patch(
            "atlas.providers._complete_with_provider", return_value=expected
        ) as mocked:
            result = complete_with("groq", "hello")
        self.assertEqual(result, expected)
        self.assertEqual(mocked.call_count, 1)

    def test_targeted_unconfigured_provider_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "vertex is not configured"):
                complete_with("vertex", "hello")

    def test_targeted_provider_error_redacts_configured_key(self):
        env = {"MISTRAL_API_KEY": "test-only-key-value"}
        with patch.dict(os.environ, env, clear=True), patch(
            "atlas.providers._complete_with_provider",
            side_effect=RuntimeError("failure test-only-key-value"),
        ):
            with self.assertRaises(RuntimeError) as raised:
                complete_with("mistral", "hello")
        self.assertNotIn("test-only-key-value", str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_provider_order_is_deduplicated(self):
        with patch.dict(os.environ, {"LLM_PROVIDER_ORDER": "groq, openrouter,groq,gemini"}, clear=False):
            self.assertEqual(_provider_order(), ["groq", "openrouter", "gemini"])

    def test_legacy_configuration_remains_supported(self):
        env = {
            "LLM_PROVIDER": "groq",
            "LLM_API_KEY": "legacy-key",
            "LLM_MODEL": "legacy-model",
            "LLM_BASE_URL": "https://legacy.example/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            config = _provider_config("groq")
        self.assertEqual(config, ProviderConfig("groq", "legacy-key", "https://legacy.example/v1", "legacy-model"))

    def test_missing_provider_is_skipped_and_next_provider_used(self):
        env = {
            "LLM_PROVIDER_ORDER": "groq,openrouter",
            "OPENROUTER_API_KEY": "router-key",
        }
        expected = ModelResponse("openrouter", "openai/gpt-4.1-mini", "ok")
        with patch.dict(os.environ, env, clear=True), patch(
            "atlas.providers._complete_with_provider", return_value=expected
        ) as mocked:
            result = complete("hello")
        self.assertEqual(result, expected)
        self.assertEqual(mocked.call_args.args[1].name, "openrouter")

    def test_runtime_failure_falls_back_to_next_provider(self):
        env = {
            "LLM_PROVIDER_ORDER": "groq,gemini",
            "GROQ_API_KEY": "groq-key",
            "GEMINI_API_KEY": "gemini-key",
        }
        fallback = ModelResponse("gemini", "gemini-2.5-flash", "fallback")
        with patch.dict(os.environ, env, clear=True), patch(
            "atlas.providers._complete_with_provider",
            side_effect=[RuntimeError("rate limited"), fallback],
        ) as mocked:
            result = complete("hello")
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(mocked.call_count, 2)

    def test_all_failures_are_aggregated_without_api_keys(self):
        env = {
            "LLM_PROVIDER_ORDER": "groq,mistral",
            "GROQ_API_KEY": "secret-groq",
            "MISTRAL_API_KEY": "secret-mistral",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "atlas.providers._complete_with_provider",
            side_effect=[RuntimeError("timeout"), RuntimeError("HTTP 503")],
        ):
            with self.assertRaisesRegex(RuntimeError, "All configured LLM providers failed") as raised:
                complete("hello")
        message = str(raised.exception)
        self.assertIn("groq: timeout", message)
        self.assertIn("mistral: HTTP 503", message)
        self.assertNotIn("secret-groq", message)
        self.assertNotIn("secret-mistral", message)


if __name__ == "__main__":
    unittest.main()
