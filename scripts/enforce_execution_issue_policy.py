#!/usr/bin/env python3
"""Close internal ATLAS execution tickets that violate the active owner strategy."""
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
MARKER = "<!-- atlas-candidate:"
REWARD_RE = re.compile(r"Reward hint:\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Z]{3,5})?", re.IGNORECASE)


def ticket_candidate(issue: dict[str, Any]) -> dict[str, Any] | None:
    body = str(issue.get("body") or "")
    if MARKER not in body:
        return None
    user = issue.get("user") or {}
    if str(user.get("login") or "") not in {"github-actions[bot]", "louis-os[bot]", "liubaining-louis"}:
        return None
    match = REWARD_RE.search(body)
    reward = float(match.group(1)) if match else None
    return {
        "title": str(issue.get("title") or ""),
        "description": body,
        "reward_amount": reward,
        "reward_verified": True,
        "payment_path": "internal_ticket_preflight_only",
        "family": "light_technical",
    }


def violation_reason(issue: dict[str, Any], policy: dict[str, Any]) -> str | None:
    candidate = ticket_candidate(issue)
    if candidate is None:
        return None
    decision = evaluate_candidate(candidate, policy)
    return None if decision.allowed else decision.reason


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


def enforce_repository(repo: str, policy: dict[str, Any]) -> dict[str, Any]:
    if "/" not in repo:
        raise ValueError("repository must be owner/name")
    base = f"https://api.github.com/repos/{repo}"
    page = 1
    inspected = 0
    closed: list[dict[str, Any]] = []
    while True:
        issues = github_json(f"{base}/issues?state=open&per_page=100&page={page}")
        if not isinstance(issues, list) or not issues:
            break
        for issue in issues:
            if not isinstance(issue, dict) or "pull_request" in issue:
                continue
            inspected += 1
            reason = violation_reason(issue, policy)
            if not reason:
                continue
            number = int(issue["number"])
            github_json(
                f"{base}/issues/{number}",
                method="PATCH",
                payload={"state": "closed", "state_reason": "not_planned"},
            )
            closed.append({"issue_number": number, "reason": reason, "title": issue.get("title")})
        if len(issues) < 100:
            break
        page += 1
    return {"inspected": inspected, "closed": closed, "closed_count": len(closed)}


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
