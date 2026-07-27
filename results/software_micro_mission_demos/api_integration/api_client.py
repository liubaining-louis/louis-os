"""Small injectable JSON API client with no embedded credentials."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.request import Request, urlopen


def fetch_json(url: str, *, opener: Callable[..., Any] = urlopen, timeout: float = 10.0) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError("url must use https")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Louis-OS-Demo/1.0"})
    with opener(request, timeout=timeout) as response:
        if getattr(response, "status", 200) >= 400:
            raise RuntimeError(f"http status {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def select_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload[field] for field in fields if field in payload}
