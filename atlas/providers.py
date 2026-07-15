from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    text: str


def _request_headers(api_key: str, provider: str) -> dict[str, str]:
    """Return explicit browser-compatible headers for OpenAI-compatible APIs.

    Some edge security layers reject Python's default ``Python-urllib`` user
    agent. Louis OS identifies itself explicitly without exposing secrets.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "LouisOS/0.7 (+https://github.com/liubaining-louis/louis-os)",
        "X-Louis-Client": "louis-os-cloud-run",
    }
    if provider.casefold() == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/liubaining-louis/louis-os"
        headers["X-Title"] = "Louis OS"
    return headers


def complete(prompt: str) -> ModelResponse:
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    base_url = os.environ.get(
        "LLM_BASE_URL", "https://api.groq.com/openai/v1"
    ).rstrip("/")
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    provider = os.environ.get("LLM_PROVIDER", "groq")

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Louis OS, an industrial and business analysis assistant. "
                        "Be precise, distinguish facts from assumptions, and never invent sources."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    request = Request(
        f"{base_url}/chat/completions",
        data=payload,
        method="POST",
        headers=_request_headers(api_key, provider),
    )

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        edge_hint = ""
        if exc.code == 403 and "1010" in details:
            edge_hint = (
                " Provider edge security rejected the client request; "
                "verify explicit User-Agent headers and provider regional access."
            )
        raise RuntimeError(
            f"LLM HTTP error {exc.code} from {provider}: {details}{edge_hint}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"LLM connection error to {provider}: {exc.reason}") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected LLM response format") from exc

    return ModelResponse(provider=provider, model=model, text=text)
