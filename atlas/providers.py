from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider_runtime import available, record_failure, record_success, trim_prompt


_SYSTEM_INSTRUCTION = (
    "You are Louis OS, an industrial and business analysis assistant. "
    "Be precise, distinguish facts from assumptions, and never invent sources."
)


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    text: str


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str


_PROVIDER_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4.1-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
}


def _request_headers(api_key: str, provider: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "LouisOS/1.0 (+https://github.com/liubaining-louis/louis-os)",
        "X-Louis-Client": "louis-os-cloud-run",
    }
    if provider.casefold() == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/liubaining-louis/louis-os"
        headers["X-Title"] = "Louis OS"
    return headers


def _provider_order() -> list[str]:
    configured = os.environ.get("LLM_PROVIDER_ORDER", "").strip()
    if configured:
        values = [item.strip().casefold() for item in configured.split(",") if item.strip()]
        return list(dict.fromkeys(values))
    return [os.environ.get("LLM_PROVIDER", "groq").strip().casefold() or "groq"]


def _vertex_configured() -> bool:
    project = os.environ.get("VERTEX_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", "")).strip()
    location = os.environ.get("VERTEX_LOCATION", "global").strip()
    model = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash").strip()
    return bool(project and location and model)


def _provider_config(name: str) -> ProviderConfig | None:
    normalized = name.strip().casefold()
    if normalized == "vertex":
        return None

    prefix = normalized.upper()
    default_base, default_model = _PROVIDER_DEFAULTS.get(normalized, ("", ""))

    api_key = os.environ.get(f"{prefix}_API_KEY", "").strip()
    base_url = os.environ.get(f"{prefix}_BASE_URL", default_base).strip().rstrip("/")
    model = os.environ.get(f"{prefix}_MODEL", default_model).strip()

    legacy_provider = os.environ.get("LLM_PROVIDER", "groq").strip().casefold()
    if normalized == legacy_provider:
        api_key = api_key or os.environ.get("LLM_API_KEY", "").strip()
        base_url = (os.environ.get("LLM_BASE_URL", "").strip() or base_url).rstrip("/")
        model = os.environ.get("LLM_MODEL", "").strip() or model

    if not api_key or not base_url or not model:
        return None
    return ProviderConfig(normalized, api_key, base_url, model)


def _complete_with_provider(prompt: str, config: ProviderConfig) -> ModelResponse:
    payload = json.dumps(
        {
            "model": config.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    request = Request(
        f"{config.base_url}/chat/completions",
        data=payload,
        method="POST",
        headers=_request_headers(config.api_key, config.name),
    )

    timeout = max(5, min(int(os.environ.get("LLM_TIMEOUT_SECONDS", "60")), 180))
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        edge_hint = ""
        if exc.code == 403 and "1010" in details:
            edge_hint = " Provider edge security rejected the client request."
        raise RuntimeError(f"HTTP {exc.code}: {details}{edge_hint}") from exc
    except URLError as exc:
        raise RuntimeError(f"connection error: {exc.reason}") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("unexpected response format") from exc
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("empty model response")
    return ModelResponse(provider=config.name, model=config.model, text=text)


def _complete_with_vertex(prompt: str) -> ModelResponse:
    project = os.environ.get("VERTEX_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", "")).strip()
    location = os.environ.get("VERTEX_LOCATION", "global").strip()
    model = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash").strip()
    if not project or not location or not model:
        raise ValueError("Vertex AI requires VERTEX_PROJECT, VERTEX_LOCATION and VERTEX_MODEL")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed") from exc

    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                temperature=0.2,
            ),
        )
        text = response.text
    except Exception as exc:
        raise RuntimeError(f"Vertex AI request failed: {exc}") from exc

    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("empty Vertex AI response")
    return ModelResponse(provider="vertex", model=model, text=text)


def complete(prompt: str) -> ModelResponse:
    prompt = trim_prompt(prompt)
    errors: list[str] = []
    configured_count = 0
    available_count = 0

    for provider_name in _provider_order():
        if not available(provider_name):
            errors.append(f"{provider_name}: temporarily unavailable or quota exhausted")
            continue
        available_count += 1

        if provider_name == "vertex":
            if not _vertex_configured():
                errors.append("vertex: not configured")
                continue
            configured_count += 1
            try:
                response = _complete_with_vertex(prompt)
                record_success(provider_name)
                return response
            except (RuntimeError, ValueError) as exc:
                record_failure(provider_name)
                errors.append(f"vertex: {exc}")
            continue

        config = _provider_config(provider_name)
        if config is None:
            errors.append(f"{provider_name}: not configured")
            continue
        configured_count += 1
        try:
            response = _complete_with_provider(prompt, config)
            record_success(provider_name)
            return response
        except (RuntimeError, ValueError) as exc:
            record_failure(provider_name)
            errors.append(f"{provider_name}: {exc}")

    if configured_count == 0 and available_count > 0:
        raise RuntimeError("No LLM provider is configured: " + "; ".join(errors))
    if available_count == 0:
        raise RuntimeError("All LLM providers are cooling down or quota-limited: " + "; ".join(errors))
    raise RuntimeError("All configured LLM providers failed: " + "; ".join(errors))


def complete_with(provider_name: str, prompt: str) -> ModelResponse:
    """Call exactly one provider, without fallback, for controlled comparisons."""

    normalized = provider_name.strip().casefold()
    if not normalized:
        raise ValueError("provider_name is required")
    if normalized == "vertex":
        if not _vertex_configured():
            raise RuntimeError("vertex is not configured")
        return _complete_with_vertex(prompt)

    config = _provider_config(normalized)
    if config is None:
        raise RuntimeError(f"{normalized} is not configured")
    try:
        return _complete_with_provider(prompt, config)
    except (RuntimeError, ValueError) as exc:
        safe_message = str(exc).replace(config.api_key, "[REDACTED]")
        raise RuntimeError(f"{normalized} request failed: {safe_message}") from exc
