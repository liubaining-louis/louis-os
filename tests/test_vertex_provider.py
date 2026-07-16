from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from google import genai
from google.genai import types

from atlas.providers import ModelResponse, _complete_with_vertex, complete


class VertexProviderTests(unittest.TestCase):
    def test_vertex_uses_application_default_identity(self) -> None:
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text="vertex answer")
            )
        )

        with patch.dict(
            os.environ,
            {
                "VERTEX_PROJECT": "test-bot-499814",
                "VERTEX_LOCATION": "global",
                "VERTEX_MODEL": "gemini-2.5-flash",
            },
            clear=False,
        ), patch.object(genai, "Client", return_value=fake_client) as client_factory, patch.object(
            types,
            "GenerateContentConfig",
            side_effect=lambda **kwargs: kwargs,
        ):
            result = _complete_with_vertex("hello")

        client_factory.assert_called_once_with(
            vertexai=True,
            project="test-bot-499814",
            location="global",
        )
        self.assertEqual(result.provider, "vertex")
        self.assertEqual(result.model, "gemini-2.5-flash")
        self.assertEqual(result.text, "vertex answer")

    def test_groq_failure_falls_back_to_vertex(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER_ORDER": "groq,vertex",
                "GROQ_API_KEY": "test-key",
                "GROQ_BASE_URL": "https://example.invalid",
                "GROQ_MODEL": "test-model",
                "VERTEX_PROJECT": "test-bot-499814",
                "VERTEX_LOCATION": "global",
                "VERTEX_MODEL": "gemini-2.5-flash",
            },
            clear=False,
        ), patch(
            "atlas.providers._complete_with_provider",
            side_effect=RuntimeError("groq unavailable"),
        ), patch(
            "atlas.providers._complete_with_vertex",
            return_value=ModelResponse("vertex", "gemini-2.5-flash", "fallback answer"),
        ):
            result = complete("analyse")

        self.assertEqual(result.provider, "vertex")
        self.assertEqual(result.text, "fallback answer")

    def test_unconfigured_vertex_is_skipped(self) -> None:
        with patch.dict(os.environ, {"LLM_PROVIDER_ORDER": "vertex"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "No LLM provider is configured"):
                complete("analyse")


if __name__ == "__main__":
    unittest.main()
