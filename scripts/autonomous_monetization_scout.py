#!/usr/bin/env python3
"""Autonomous evidence-first monetization worker with a non-blocking decision engine.

The worker continuously searches public GitHub issues for explicit paid opportunities,
qualifies them, prepares actionable dossiers, records evidence and publishes live state.
It never submits account-bound work, accepts legal terms, spends money or claims revenue
without proof. Human confirmation is a gate only for the sensitive action itself; it does
not stop research, preparation, prioritisation or subsequent scout cycles.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.opportunity_readiness import assess_opportunity_readiness

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")

QUERIES = [
    'is:issue is:open (bounty OR reward) in:title,body archived:false',
    'is:issue is:open "paid" in:title label:bounty archived:false',
    'is:issue is:open (prize OR stipend) in:title,body archived:false',
    'is:issue is:open (grant OR compensation) in:title,body archived:false',
]
MONEY_RE = re.compile(
    r"(?:[$€£]\s?([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s?(USD|EUR|GBP))",
    re.I,
)


def github_get(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-autonomous-monetization-worker",
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
    currency = (
        match.group(3)
        or ("USD" if "$" in match.group(0) else "EUR" if "€" in match.group(0) else "GBP")
    ).upper()
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
    if any(term in text.lower() for term in ("good first issue", "beginner", "documentation", "python", "api")):
        value += 10.0
    if any(term in text.lower() for term in ("closed bounty", "already claimed", "winner selected")):
        value -= 35.0
    return round(max(0.0, min(value, 100.0)), 1)


def candidate_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def build_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    """Classify what Louis OS may do now without blocking on a human."""
    autonomous_actions = [
        "preserve source evidence",
        "analyse scope and reward signal",
        "prepare an execution checklist",
        "estimate feasibility and risks",
        "continue scouting other opportunities",
    ]
    gated_actions = [
        "authenticate to a third-party account",
        "post a claim, application, comment or submission",
        "accept legal terms or transfer intellectual property",
        "spend money or incur a financial commitment",
    ]
    return {
        "candidate_id": candidate["id"],
        "decision": "prepare_and_continue",
        "autonomous_now": autonomous_actions,
        "human_gate_only_for": gated_actions,
        "blocked": False,
        "reason": "All reversible research and preparation actions are allowed; only external account-bound or irreversible actions require confirmation.",
    }


def build_dossier(candidate: dict[str, Any], now: str) -> dict[str, Any]:
    reward = candidate.get("reward_hint", 0.0)
    return {
        "candidate_id": candidate["id"],
        "prepared_at": now,
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
        "reward_hint": reward,
        "currency": candidate.get("currency", "unknown"),
        "score": candidate.get("score", 0.0),
        "status": "prepared_for_execution_review",
        "execution_checklist": [
            "Read the full issue and repository contribution rules",
            "Confirm the bounty is still open and unclaimed",
            "Identify expected deliverable and acceptance criteria",
            "Estimate implementation effort and technical fit",
            "Prepare a draft solution plan and validation evidence",
            "Request confirmation only immediately before an external submission or account action",
        ],
        "risk_flags": [
            "account-bound submission required" if candidate.get("requires_account") else "none detected",
            "reward is a hint until confirmed by authoritative source" if reward else "reward amount not verified",
        ],
    }


def publish_runtime_state(
    cycle: dict[str, Any], candidates: list[dict[str, Any]], decisions: list[dict[str, Any]], dossiers: list[dict[str, Any]]
) -> None:
    try:
        db = firestore.Client(project=PROJECT_ID)
        state = {
            "worker_status": "running",
            "worker_verified": True,
            "autonomous_decision_engine": "active",
            "waiting_for_instruction": False,
            "last_cycle_at": cycle["timestamp"],
            "last_cycle_status": cycle["status"],
            "sources_checked": cycle["sources_checked"],
            "opportunities_qualified": cycle["opportunities_qualified"],
            "candidates_prepared": cycle["candidates_prepared"],
            "autonomous_actions_completed": cycle["autonomous_actions_completed"],
            "actions_submitted": cycle["actions_submitted"],
            "revenue_confirmed_eur": cycle["revenue_confirmed_eur"],
            "top_candidate": cycle.get("top_candidate"),
            "current_activity": "Preparing qualified opportunities and continuing discovery cycles.",
            "next_action": "Continue autonomous research, refresh rankings and deepen candidate dossiers; request confirmation only at the exact external submission gate.",
            "human_gate_pending": bool(candidates),
            "human_gate_scope": "External account-bound submission only",
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("louis_runtime").document("current").set(state, merge=True)
        cycle_id = cycle["timestamp"].replace(":", "-")
        db.collection("louis_worker_cycles").document(cycle_id).set(cycle)
        for decision in decisions:
            db.collection("louis_autonomous_decisions").document(decision["candidate_id"]).set(
                {**decision, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True
            )
        for dossier in dossiers:
            db.collection("louis_candidate_dossiers").document(dossier["candidate_id"]).set(
                {**dossier, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True
            )
    except Exception as exc:
        print(json.dumps({"firestore_publish_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for query in QUERIES:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 20}
        )
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
            attractiveness_score = score(item)
            readiness = assess_opportunity_readiness(item, attractiveness_score)
            found[html_url] = {
                "id": candidate_id(html_url),
                "source": "github_public_issue",
                "title": item.get("title", ""),
                "url": html_url,
                "repository_url": item.get("repository_url", ""),
                "updated_at": item.get("updated_at"),
                "reward_hint": amount,
                "currency": currency,
                "comments": item.get("comments", 0),
                "score": attractiveness_score,
                "execution_score": readiness.execution_score,
                "readiness_status": readiness.status,
                "external_prerequisites": list(readiness.external_prerequisites),
                "external_prerequisite_evidence": list(readiness.evidence),
                "external_prerequisites_cleared": readiness.executable_now,
                "requires_account": "third_party_account_required" in readiness.external_prerequisites,
                "requires_user_validation": not readiness.executable_now,
                "status": "qualified_executable" if readiness.executable_now else "qualified_gated",
            }

    candidates = sorted(
        found.values(),
        key=lambda x: (
            x["readiness_status"] != "executable_now",
            -x["execution_score"],
            -x["score"],
            x["id"],
        ),
    )[:10]
    executable_candidates = [item for item in candidates if item["readiness_status"] == "executable_now"]
    decisions = [build_decision(candidate) for candidate in candidates]
    dossiers = [build_dossier(candidate, now) for candidate in candidates[:5]]

    (RESULTS / "monetization_candidates.json").write_text(
        json.dumps(
            {
                "generated_at": now,
                "count": len(candidates),
                "candidates": candidates,
                "decisions": decisions,
                "dossiers_prepared": len(dossiers),
                "errors": errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (RESULTS / "candidate_dossiers.json").write_text(
        json.dumps({"generated_at": now, "dossiers": dossiers}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    cycle = {
        "timestamp": now,
        "type": "autonomous_decision_and_monetization_cycle",
        "sources_checked": len(QUERIES),
        "opportunities_qualified": len(candidates),
        "candidates_prepared": len(dossiers),
        "autonomous_actions_completed": len(decisions) + len(dossiers),
        "actions_submitted": 0,
        "revenue_confirmed_eur": 0.0,
        "waiting_for_instruction": False,
        "status": "completed_and_continuing" if candidates else "no_verified_candidate_continuing",
        "top_candidate": executable_candidates[0] if executable_candidates else None,
        "gated_candidates": len(candidates) - len(executable_candidates),
        "errors": errors,
    }
    with (RESULTS / "monetization_experiments.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(cycle, ensure_ascii=False) + "\n")
    with (RESULTS / "evidence.jsonl").open("a", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(
                json.dumps(
                    {
                        "timestamp": now,
                        "kind": "public_opportunity",
                        "url": candidate["url"],
                        "title": candidate["title"],
                        "source": candidate["source"],
                        "candidate_id": candidate["id"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    ledger_path = RESULTS / "monetization.json"
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {}
    ledger.update(
        {
            "updated_at": now,
            "status": "active",
            "worker_waiting": False,
            "autonomous_decision_engine": "active",
            "revenue_received": float(ledger.get("revenue_received", 0.0)),
            "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0)),
            "internet_opportunities_qualified": len(candidates),
            "candidates_prepared": len(dossiers),
            "autonomous_actions_completed": len(decisions) + len(dossiers),
            "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)),
            "top_opportunity": executable_candidates[0] if executable_candidates else None,
            "gated_opportunities": len(candidates) - len(executable_candidates),
            "next_action": (
                "Advance the highest-ranked executable opportunity."
                if executable_candidates
                else "Continue scouting for an opportunity without unmet external prerequisites."
            ),
        }
    )
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish_runtime_state(cycle, candidates, decisions, dossiers)
    print(json.dumps(cycle, ensure_ascii=False))


if __name__ == "__main__":
    main()
