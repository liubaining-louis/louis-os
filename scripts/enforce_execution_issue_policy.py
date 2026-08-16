#!/usr/bin/env python3
"""Close internal ATLAS execution tickets that are stale, unsafe or duplicated."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.production_policy import evaluate_candidate, load_policy

POLICY_PATH = ROOT / "config" / "production_policy.json"
CANDIDATE_RE = re.compile(r"<!--\s*atlas-candidate:([^>\s]+)\s*-->", re.IGNORECASE)
REWARD_RE = re.compile(r"Reward hint:\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Z]{3,5})?", re.IGNORECASE)
POLICY_RE = re.compile(r"Production policy:\s*`([^`]+)`", re.IGNORECASE)
PAYMENT_AUTHORITY_MARKER = "Payment authority: verified"
INTERNAL_ACTORS = {"github-actions[bot]", "louis-os[bot]", "liubaining-louis"}


def candidate_marker(issue: dict[str, Any]) -> str | None:
    body = str(issue.get("body") or "")
    user = issue.get("user") or {}
    if str(user.get("login") or "") not in INTERNAL_ACTORS:
        return None
    match = CANDIDATE_RE.search(body)
    return match.group(1).strip() if match else None


def ticket_policy_contract(issue: dict[str, Any]) -> tuple[str | None, bool]:
    body = str(issue.get("body") or "")
    policy_match = POLICY_RE.search(body)
    policy_mode = policy_match.group(1).strip() if policy_match else None
    payment_verified = PAYMENT_AUTHORITY_MARKER.lower() in body.lower()
    return policy_mode, payment_verified


def ticket_candidate(issue: dict[str, Any]) -> dict[str, Any] | None:
    marker = candidate_marker(issue)
    if not marker:
        return None
    body = str(issue.get("body") or "")
    match = REWARD_RE.search(body)
    reward = float(match.group(1)) if match else None
    _, payment_verified = ticket_policy_contract(issue)
    return {
        "title": str(issue.get("title") or ""),
        "description": body,
        "reward_amount": reward,
        "reward_verified": payment_verified,
        "payment_path": "verified_internal_execution_contract" if payment_verified else None,
        "family": "light_technical",
    }


def violation_reason(issue: dict[str, Any], policy: dict[str, Any]) -> str | None:
    candidate = ticket_candidate(issue)
    if candidate is None:
        return None
    policy_mode, payment_verified = ticket_policy_contract(issue)
    if not payment_verified:
        return "legacy_pre_payment_authority_policy_ticket"
    if policy_mode != str(policy.get("mode") or ""):
        return "stale_production_policy_contract"
    decision = evaluate_candidate(candidate, policy)
    return None if decision.allowed else decision.reason


def plan_issue_actions(issues: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic close actions without mutating the input collection.

    Legacy/policy violations take precedence. For current-policy duplicate ATLAS
    tickets, keep only the newest issue number for each candidate marker.
    """
    internal: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        if candidate_marker(issue):
            internal.append(issue)

    newest_by_marker: dict[str, int] = {}
    for issue in internal:
        marker = candidate_marker(issue)
        if marker:
            newest_by_marker[marker] = max(newest_by_marker.get(marker, 0), int(issue.get("number") or 0))

    actions: list[dict[str, Any]] = []
    for issue in internal:
        number = int(issue.get("number") or 0)
        marker = candidate_marker(issue) or ""
        reason = violation_reason(issue, policy)
        if reason:
            actions.append({
                "issue_number": number,
                "reason": reason,
                "candidate_id": marker,
                "title": issue.get("title"),
            })
            continue
        if number != newest_by_marker.get(marker):
            actions.append({
                "issue_number": number,
                "reason": "duplicate_internal_candidate_ticket",
                "candidate_id": marker,
                "title": issue.get("title"),
            })
    actions.sort(key=lambda item: int(item["issue_number"]), reverse=True)
    return actions


def github_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    token = os.getenv("GITHUB_TOKEN", "")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}" if token else "",
            "User-Agent": "louis-os-production-policy-enforcer",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def fetch_open_issue_snapshot(base: str) -> list[dict[str, Any]]:
    """Snapshot every currently open issue before any mutation to avoid pagination skips."""
    snapshot: list[dict[str, Any]] = []
    page = 1
    while True:
        issues = github_json(f"{base}/issues?state=open&per_page=100&page={page}")
        if not isinstance(issues, list) or not issues:
            break
        snapshot.extend(item for item in issues if isinstance(item, dict))
        if len(issues) < 100:
            break
        page += 1
        if page > 50:
            raise RuntimeError("open issue pagination exceeded bounded 5000-item safety limit")
    return snapshot


def enforce_repository(repo: str, policy: dict[str, Any]) -> dict[str, Any]:
    if "/" not in repo:
        raise ValueError("repository must be owner/name")
    base = f"https://api.github.com/repos/{repo}"
    snapshot = fetch_open_issue_snapshot(base)
    actions = plan_issue_actions(snapshot, policy)
    closed: list[dict[str, Any]] = []
    for action in actions:
        number = int(action["issue_number"])
        github_json(
            f"{base}/issues/{number}",
            method="PATCH",
            payload={"state": "closed", "state_reason": "not_planned"},
        )
        closed.append(action)
    return {
        "inspected": sum(1 for item in snapshot if isinstance(item, dict) and "pull_request" not in item),
        "internal_candidates_seen": sum(1 for item in snapshot if candidate_marker(item)),
        "closed": closed,
        "closed_count": len(closed),
        "legacy_closed_count": sum(1 for item in closed if item["reason"] == "legacy_pre_payment_authority_policy_ticket"),
        "policy_closed_count": sum(1 for item in closed if item["reason"] not in {"duplicate_internal_candidate_ticket", "legacy_pre_payment_authority_policy_ticket"}),
        "duplicate_closed_count": sum(1 for item in closed if item["reason"] == "duplicate_internal_candidate_ticket"),
    }


def main() -> int:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is required")
    policy = load_policy(POLICY_PATH)
    result = enforce_repository(repo, policy)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
