from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass
class ProviderState:
    calls: int = 0
    failures: int = 0
    blocked_until: float = 0.0


_LOCK = threading.Lock()
_STATES: dict[str, ProviderState] = {}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def state_for(provider: str) -> ProviderState:
    with _LOCK:
        return _STATES.setdefault(provider, ProviderState())


def available(provider: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    state = state_for(provider)
    max_calls = _int_env(f"{provider.upper()}_MAX_CALLS_PER_INSTANCE", 0, 0, 100000)
    if max_calls and state.calls >= max_calls:
        return False
    return state.blocked_until <= now


def record_success(provider: str) -> None:
    with _LOCK:
        state = _STATES.setdefault(provider, ProviderState())
        state.calls += 1
        state.failures = 0
        state.blocked_until = 0.0


def record_failure(provider: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    threshold = _int_env("LLM_FAILURES_BEFORE_COOLDOWN", 2, 1, 20)
    cooldown = _int_env("LLM_PROVIDER_COOLDOWN_SECONDS", 120, 1, 3600)
    with _LOCK:
        state = _STATES.setdefault(provider, ProviderState())
        state.calls += 1
        state.failures += 1
        if state.failures >= threshold:
            state.blocked_until = now + cooldown


def reset_states() -> None:
    with _LOCK:
        _STATES.clear()


def trim_prompt(prompt: str) -> str:
    limit = _int_env("LLM_MAX_PROMPT_CHARS", 48000, 2000, 500000)
    if len(prompt) <= limit:
        return prompt
    head = int(limit * 0.65)
    tail = limit - head
    return prompt[:head] + "\n[context truncated by Louis OS token budget]\n" + prompt[-tail:]
