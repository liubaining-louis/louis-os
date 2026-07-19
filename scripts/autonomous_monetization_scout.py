#!/usr/bin/env python3
"""Autonomous, evidence-first monetization scout.

Searches public GitHub issues for explicit bounty/reward opportunities, scores them,
records verifiable evidence, updates the dashboard ledger, and publishes each cycle
to Firestore so the Louis OS chat can report live activity.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")

QUERIES = [
    'is:issue is:open (bounty OR reward) in:title,body archived:false',
    'is:issue is:open "paid" in:title label:bounty archived:false',
    'is:issue is:open (prize OR stipend) in:title,body archived:false',
]
MONEY_RE = re.compile(r"(?:[$€£]\s?([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s?(USD|EUR|GBP))", re.I)


def github_get(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-autonomous-monetization-scout",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def reward_hint(text: str) -> tuple[float, str]:
    match = MONEY_RE.search(text or "")
    if not match:
        return 0.0, "unknown"
    raw = (match.group(1) or match.group(2) or "0").replace(",", "")
    currency = (match.group(3) or ("USD" if "$" in match.group(0) else "EUR" if "€" in match.group(0) else "GBP")).upper()
    try:
        return float(raw), currency
    except ValueError:
        return 0.0, currency


def score(item: dict[str, Any]) -> float:
    text = f"{item.get('title', '')} {item.get('body', '')}"
    amount, _ = reward_hint(text)
    value = 20.0 + (min(40.0, amount / 25.0) if amount > 0 else 0.0)
    labels = {str(x.get("name", "")).lower() for x in item.get("labels", [])}
    if "bounty" in labels or "reward" in labels:
        value += 20.0
    if item.get("comments", 0) < 5:
        value += 10.0
    if any(term in text.lower() for term in ("good first issue", "beginner", "documentation", "python")):
        value += 10.0
    return round(min(value, 100.0), 1)


def publish_runtime_state(cycle: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    """Publish live state without making Firestore failure hide the completed cycle."""
    try:
        db = firestore.Client(project=PROJECT_ID)
        state = {
            "worker_status": "running",
            "worker_verified": True,
            "last_cycle_at": cycle["timestamp"],
            "last_cycle_status": cycle["status"],
            "sources_checked": cycle["sources_checked"],
            "opportunities_qualified": cycle["opportunities_qualified"],
            "actions_submitted": cycle["actions_submitted"],
            "revenue_confirmed_eur": cycle["revenue_confirmed_eur"],
            "top_candidate": cycle.get("top_candidate"),
            "next_action": (
                "Review the highest-scoring candidate; request confirmation before any account-bound submission."
                if candidates else "Expand public opportunity sources and continue scouting."
            ),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("louis_runtime").document("current").set(state, merge=True)
        db.collection("louis_worker_cycles").document(cycle["timestamp"].replace(":", "-")).set(cycle)
    except Exception as exc:
        print(json.dumps({"firestore_publish_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for query in QUERIES:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({
            "q": query, "sort": "updated", "order": "desc", "per_page": 20,
        })
        try:
            payload = github_get(url)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")
            continue
        for item in payload.get("items", []):
            html_url = item.get("html_url")
            if not html_url:
                continue
            text = f"{item.get('title', '')}\n{item.get('body', '')}"
            amount, currency = reward_hint(text)
            found[html_url] = {
                "source": "github_public_issue",
                "title": item.get("title", ""),
                "url": html_url,
                "repository_url": item.get("repository_url", ""),
                "updated_at": item.get("updated_at"),
                "reward_hint": amount,
                "currency": currency,
                "comments": item.get("comments", 0),
                "score": score(item),
                "requires_account": True,
                "requires_user_validation": True,
                "status": "qualified_not_submitted",
            }

    candidates = sorted(found.values(), key=lambda x: x["score"], reverse=True)[:10]
    (RESULTS / "monetization_candidates.json").write_text(
        json.dumps({"generated_at": now, "count": len(candidates), "candidates": candidates, "errors": errors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    cycle = {
        "timestamp": now,
        "type": "autonomous_internet_scout",
        "sources_checked": len(QUERIES),
        "opportunities_qualified": len(candidates),
        "actions_submitted": 0,
        "revenue_confirmed_eur": 0.0,
        "status": "completed" if candidates else "no_verified_candidate",
        "top_candidate": candidates[0] if candidates else None,
        "errors": errors,
    }
    with (RESULTS / "monetization_experiments.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(cycle, ensure_ascii=False) + "\n")
    with (RESULTS / "evidence.jsonl").open("a", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps({
                "timestamp": now, "kind": "public_opportunity", "url": candidate["url"],
                "title": candidate["title"], "source": candidate["source"],
            }, ensure_ascii=False) + "\n")

    ledger_path = RESULTS / "monetization.json"
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {}
    ledger.update({
        "updated_at": now,
        "status": "active",
        "revenue_received": float(ledger.get("revenue_received", 0.0)),
        "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0)),
        "internet_opportunities_qualified": len(candidates),
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)),
        "top_opportunity": candidates[0] if candidates else None,
        "next_action": "Review top candidate and obtain validation for any account-bound submission" if candidates else "Expand verified public sources",
    })
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish_runtime_state(cycle, candidates)
    print(json.dumps(cycle, ensure_ascii=False))


if __name__ == "__main__":
    main()
