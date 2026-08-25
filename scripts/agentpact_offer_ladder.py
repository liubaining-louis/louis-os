#!/usr/bin/env python3
"""Maintain Louis OS's bounded, non-financial AgentPact seller presence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("AGENTPACT_BASE_URL", "https://api.agentpact.xyz/api").rstrip("/")
IDENTITY_ENV = Path(os.environ.get("AGENTPACT_IDENTITY_ENV", "/var/lib/louis-os/secrets/agentpact.env"))
RESULT_PATH = Path(
    os.environ.get(
        "AGENTPACT_SELLER_RESULT",
        "/var/lib/louis-os/results/agentpact-seller/offer_ladder.json",
    )
)
MAX_ACTIVE_OFFERS = 15
TRANSIENT_ATTEMPTS = 3

DESIRED_OFFERS: tuple[dict[str, Any], ...] = (
    {
        "title": "Louis OS Tested Python/API Automation Sprint",
        "descriptionMd": (
            "A bounded Python/API automation sprint: one small integration, data transform, "
            "or reliability fix with tests, usage notes, and reproducible evidence. Scope is "
            "confirmed before work; no credential harvesting, spam, CAPTCHA bypass, funding, "
            "wallet signing, or unauthorized access."
        ),
        "category": "data",
        "tags": ["python", "api", "csv", "json", "automation", "testing"],
        "basePrice": 15.0,
        "maxPriceDeltaPct": 20,
        "fulfillmentType": "generic",
        "slaDays": 2,
    },
    {
        "title": "Louis OS Evidence-Backed Technical Research Brief",
        "descriptionMd": (
            "A concise technical research brief with cited primary sources, explicit assumptions, "
            "and a decision-ready recommendation. Includes a structured Markdown report and source "
            "list; excludes private-data collection, fabricated evidence, promotion, and financial "
            "or legal commitments."
        ),
        "category": "data",
        "tags": ["research", "analysis", "report", "evidence", "technical"],
        "basePrice": 25.0,
        "maxPriceDeltaPct": 20,
        "fulfillmentType": "generic",
        "slaDays": 2,
    },
)


def load_shell_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        parts = shlex.split(raw_value, comments=True, posix=True)
        values[key] = parts[0] if parts else ""
    return values


def is_transient_http_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def is_idempotent_offer_conflict(status: int) -> bool:
    return status == 409


def request_json(
    method: str,
    path: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "x-api-key": api_key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    for attempt in range(TRANSIENT_ATTEMPTS):
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"error": raw[:500]}
            if is_transient_http_status(exc.code) and attempt + 1 < TRANSIENT_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            return exc.code, parsed
        except URLError as exc:
            if attempt + 1 < TRANSIENT_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            return 599, {"error": type(exc.reason).__name__}
    return 599, {"error": "request_exhausted"}


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def extract_offers(payload: Any) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in walk_dicts(payload):
        title = obj.get("title")
        offer_id = obj.get("id") or obj.get("offerId") or obj.get("offer_id")
        if not isinstance(title, str) or offer_id is None:
            continue
        marker = str(offer_id)
        if marker in seen:
            continue
        seen.add(marker)
        offers.append(obj)
    return offers


def owner_id(offer: dict[str, Any]) -> str:
    for key in ("agentId", "agent_id", "sellerAgentId", "seller_agent_id"):
        if offer.get(key) is not None:
            return str(offer[key])
    seller = offer.get("seller")
    if isinstance(seller, dict):
        return str(seller.get("id") or seller.get("agentId") or "")
    return ""


def own_offers(payload: Any, agent_id: str) -> list[dict[str, Any]]:
    return [offer for offer in extract_offers(payload) if owner_id(offer) == agent_id]


def response_id(payload: Any) -> str | None:
    for obj in walk_dicts(payload):
        for key in ("id", "offerId", "offer_id"):
            if obj.get(key):
                return str(obj[key])
    return None


def write_snapshot(snapshot: dict[str, Any]) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RESULT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(RESULT_PATH)


def main() -> int:
    snapshot: dict[str, Any] = {
        "market": "agentpact",
        "mode": "seller_offer_ladder",
        "financial_actions_allowed": False,
        "desired_prices_usdc": [offer["basePrice"] for offer in DESIRED_OFFERS],
        "created": [],
        "reused": [],
        "errors": [],
    }
    if not IDENTITY_ENV.is_file():
        snapshot["status"] = "identity_missing"
        snapshot["errors"].append("agentpact_identity_missing")
        write_snapshot(snapshot)
        return 2

    identity = load_shell_env(IDENTITY_ENV)
    agent_id = identity.get("AGENTPACT_AGENT_ID", "")
    api_key = identity.get("AGENTPACT_API_KEY", "")
    if not agent_id or not api_key:
        snapshot["status"] = "identity_invalid"
        snapshot["errors"].append("agentpact_identity_incomplete")
        write_snapshot(snapshot)
        return 2

    heartbeat_status, _ = request_json("POST", f"/agents/{agent_id}/heartbeat", api_key, {})
    snapshot["heartbeat_http"] = heartbeat_status

    inventory_status, inventory_payload = request_json("GET", "/offers/grouped", api_key)
    snapshot["inventory_http"] = inventory_status
    if inventory_status in (401, 403):
        snapshot["status"] = "authentication_blocked"
        snapshot["errors"].append(f"inventory_http_{inventory_status}")
        write_snapshot(snapshot)
        return 3
    if not 200 <= inventory_status < 300:
        snapshot["status"] = "temporarily_unavailable" if is_transient_http_status(inventory_status) else "inventory_blocked"
        snapshot["errors"].append(f"inventory_http_{inventory_status}")
        write_snapshot(snapshot)
        return 0 if is_transient_http_status(inventory_status) else 4

    existing = own_offers(inventory_payload, agent_id)
    snapshot["existing_owned_offer_count"] = len(existing)
    titles = {str(offer.get("title", "")).strip() for offer in existing}
    for desired in DESIRED_OFFERS:
        title = desired["title"]
        if title in titles:
            match = next(offer for offer in existing if str(offer.get("title", "")).strip() == title)
            snapshot["reused"].append(
                {"title": title, "offer_id": response_id(match), "price_usdc": desired["basePrice"]}
            )
            continue
        if len(existing) + len(snapshot["created"]) >= MAX_ACTIVE_OFFERS:
            snapshot["errors"].append("active_offer_cap_reached")
            break
        payload = {"agentId": agent_id, **desired}
        status, response = request_json("POST", "/offers", api_key, payload)
        if is_idempotent_offer_conflict(status):
            snapshot["reused"].append(
                {
                    "title": title,
                    "offer_id": response_id(response),
                    "price_usdc": desired["basePrice"],
                    "source": "create_conflict",
                }
            )
            continue
        if status in (401, 403):
            snapshot["errors"].append(f"create_http_{status}")
            snapshot["status"] = "authentication_blocked"
            write_snapshot(snapshot)
            return 3
        if not 200 <= status < 300:
            snapshot["errors"].append(f"create_http_{status}:{title}")
            if is_transient_http_status(status):
                snapshot["status"] = "temporarily_unavailable"
                write_snapshot(snapshot)
                return 0
            continue
        snapshot["created"].append(
            {"title": title, "offer_id": response_id(response), "price_usdc": desired["basePrice"], "http": status}
        )

    snapshot["status"] = "active" if not snapshot["errors"] else "partial"
    snapshot["financial_actions_attempted"] = 0
    snapshot["deal_proposals_attempted"] = 0
    write_snapshot(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
