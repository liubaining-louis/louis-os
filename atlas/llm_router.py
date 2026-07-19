"""Adaptive multi-provider LLM router for Louis OS.

Providers are tried in a task-aware order. Missing credentials and provider failures are
recorded as attempts, then the router falls back without interrupting the chat.
No API key or full prompt is written to Firestore.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.cloud import firestore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
GEMINI_MODEL = os.getenv("LOUIS_GEMINI_MODEL", os.getenv("LOUIS_CHAT_MODEL", "gemini-2.5-flash"))
QWEN_MODEL = os.getenv("LOUIS_QWEN_MODEL", "qwen/qwen3-30b-a3b-instruct-2507")
GROQ_MODEL = os.getenv("LOUIS_GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TIMEOUT = int(os.getenv("LOUIS_PROVIDER_TIMEOUT", "45"))


@dataclass
class RoutedResponse:
    text: str
    provider: str
    model: str


class _ModelsFacade:
    def __init__(self, router: "LLMRouter") -> None:
        self._router = router

    def generate_content(self, *, model: str | None = None, contents: Any = "", **_: Any) -> RoutedResponse:
        return self._router.generate(str(contents), requested_model=model)


class RoutedClient:
    """Compatibility facade matching google-genai's client.models.generate_content API."""

    def __init__(self) -> None:
        self.router = LLMRouter()
        self.models = _ModelsFacade(self.router)


class LLMRouter:
    def __init__(self) -> None:
        self._gemini = genai.Client()
        self._db: firestore.Client | None = None

    def _firestore(self) -> firestore.Client:
        if self._db is None:
            self._db = firestore.Client(project=PROJECT_ID)
        return self._db

    @staticmethod
    def _task(prompt: str) -> str:
        text = prompt.casefold()
        if any(word in text for word in ("prospection", "commercial", "client", "monétisation", "opportunité", "vente")):
            return "commercial"
        if any(word in text for word in ("code", "python", "github", "debug", "fonction", "api")):
            return "code"
        if any(word in text for word in ("recherche web", "résultats web", "sources", "actualité", "internet")):
            return "research"
        if len(prompt) < 1200:
            return "fast_chat"
        return "general"

    @staticmethod
    def _order(task: str) -> list[str]:
        if task == "commercial":
            return ["qwen", "gemini", "groq"]
        if task == "fast_chat":
            return ["groq", "gemini", "qwen"]
        if task == "code":
            return ["gemini", "qwen", "groq"]
        return ["gemini", "qwen", "groq"]

    @staticmethod
    def _openai_compatible(url: str, api_key: str, model: str, prompt: str, extra_headers: dict[str, str] | None = None) -> str:
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Louis-OS-LLM-Router/1.0",
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = json.load(response)
        return str(payload["choices"][0]["message"]["content"]).strip()

    def _call(self, provider: str, prompt: str) -> tuple[str, str]:
        if provider == "gemini":
            result = self._gemini.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return (result.text or "").strip(), GEMINI_MODEL
        if provider == "qwen":
            if not OPENROUTER_API_KEY:
                raise RuntimeError("OPENROUTER_API_KEY missing")
            text = self._openai_compatible(
                "https://openrouter.ai/api/v1/chat/completions",
                OPENROUTER_API_KEY,
                QWEN_MODEL,
                prompt,
                {"HTTP-Referer": "https://github.com/liubaining-louis/louis-os", "X-Title": "Louis OS"},
            )
            return text, QWEN_MODEL
        if provider == "groq":
            if not GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY missing")
            text = self._openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions",
                GROQ_API_KEY,
                GROQ_MODEL,
                prompt,
            )
            return text, GROQ_MODEL
        raise ValueError(f"Unknown provider: {provider}")

    def _record(self, payload: dict[str, Any]) -> None:
        try:
            self._firestore().collection("louis_llm_calls").add(payload)
        except Exception:
            pass

    def generate(self, prompt: str, requested_model: str | None = None) -> RoutedResponse:
        task = self._task(prompt)
        attempts: list[dict[str, Any]] = []
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        for provider in self._order(task):
            started = time.monotonic()
            try:
                text, model = self._call(provider, prompt)
                latency_ms = round((time.monotonic() - started) * 1000)
                if not text:
                    raise RuntimeError("empty response")
                attempts.append({"provider": provider, "model": model, "ok": True, "latency_ms": latency_ms})
                self._record({
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "task": task,
                    "selected_provider": provider,
                    "selected_model": model,
                    "requested_model": requested_model or "",
                    "prompt_sha256": prompt_hash,
                    "prompt_chars": len(prompt),
                    "response_chars": len(text),
                    "attempts": attempts,
                })
                return RoutedResponse(text=text, provider=provider, model=model)
            except Exception as exc:
                attempts.append({
                    "provider": provider,
                    "ok": False,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                })

        self._record({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "selected_provider": "none",
            "prompt_sha256": prompt_hash,
            "prompt_chars": len(prompt),
            "attempts": attempts,
        })
        raise RuntimeError("All configured LLM providers failed")


def provider_status() -> dict[str, Any]:
    return {
        "router": "adaptive",
        "gemini": {"configured": True, "model": GEMINI_MODEL},
        "qwen": {"configured": bool(OPENROUTER_API_KEY), "model": QWEN_MODEL, "provider": "OpenRouter"},
        "groq": {"configured": bool(GROQ_API_KEY), "model": GROQ_MODEL},
        "fallback_orders": {
            "commercial": ["qwen", "gemini", "groq"],
            "fast_chat": ["groq", "gemini", "qwen"],
            "code": ["gemini", "qwen", "groq"],
            "general": ["gemini", "qwen", "groq"],
        },
    }
