from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

BASE_URL = os.getenv("SUPERTEAM_BASE_URL", "https://superteam.fun").rstrip("/")


@dataclass(frozen=True)
class SuperteamResponse:
    status: int
    payload: dict[str, Any]


def _request(method: str, path: str, *, api_key: str | None = None, payload: dict[str, Any] | None = None) -> SuperteamResponse:
    headers = {"Accept": "application/json", "User-Agent": "LouisOS/1.0"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(f"{BASE_URL}{path}", data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return SuperteamResponse(resp.status, parsed if isinstance(parsed, dict) else {"data": parsed})
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"superteam_http_{exc.code}:{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"superteam_connection_error:{exc.reason}") from exc


def register_agent(name: str = "louis-os-agent") -> dict[str, Any]:
    return _request("POST", "/api/agents", payload={"name": name}).payload


def live_listings(api_key: str, *, take: int = 20) -> dict[str, Any]:
    take = min(max(int(take), 1), 100)
    return _request("GET", f"/api/agents/listings/live?take={take}", api_key=api_key).payload


def listing_details(api_key: str, slug: str) -> dict[str, Any]:
    return _request("GET", f"/api/agents/listings/details/{slug}", api_key=api_key).payload


def create_submission(
    api_key: str,
    *,
    listing_id: str,
    link: str,
    other_info: str,
    eligibility_answers: list[dict[str, str]] | None = None,
    ask: str | int | float | None = None,
    telegram: str | None = None,
    tweet: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "listingId": listing_id,
        "link": link,
        "tweet": tweet,
        "otherInfo": other_info,
        "eligibilityAnswers": eligibility_answers or [],
        "ask": ask,
    }
    if telegram:
        payload["telegram"] = telegram
    return _request("POST", "/api/agents/submissions/create", api_key=api_key, payload=payload).payload
