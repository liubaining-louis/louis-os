"""Canonical GitHub issue verification for platform-derived paid opportunities."""
from __future__ import annotations

from dataclasses import replace
import json
import os
import re
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity


Fetcher = Callable[[str], bytes]
_ISSUE_RE = re.compile(r"^/([^/]+)/([^/]+)/issues/(\d+)$")
_ATTEMPT_RE = re.compile(r"(?im)^\s*/attempt\s+#?\d+")
_SOLUTION_RE = re.compile(r"(?i)(submitted fix here|opened PR\s+#?\d+|solution\s*:\s*https://github\.com/.+/pull/\d+)")


def _default_fetcher(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("GitHub verifier only permits api.github.com")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Louis-OS-Cash-First/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=20.0) as response:  # nosec B310: fixed host
        return response.read(1_000_001)


def _audit_bounty_comments(
    opportunity: InternetOpportunity,
    payload: dict,
    *,
    fetcher: Fetcher,
) -> dict[str, int] | None:
    """Return bounded competition evidence, or None when the bounty is exhausted/crowded.

    Only platform-derived Algora opportunities use this extra audit. The official
    GitHub comments endpoint is treated as the source of truth for prior attempts,
    submitted solutions and Algora reward receipts.
    """
    if opportunity.source_id != "algora_public_bounties":
        return {"attempt_count": 0, "submitted_solution_count": 0, "reward_receipt_count": 0}
    comments_url = str(payload.get("comments_url") or "").strip()
    if not comments_url:
        # Older fixtures and nonstandard payloads keep canonical state verification;
        # production GitHub payloads always expose comments_url.
        return {"attempt_count": 0, "submitted_solution_count": 0, "reward_receipt_count": 0}
    try:
        comments = json.loads(fetcher(comments_url).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(comments, list):
        return None

    attempt_count = 0
    submitted_solution_count = 0
    reward_receipt_count = 0
    for item in comments:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "")
        login = str((item.get("user") or {}).get("login") or "") if isinstance(item.get("user"), dict) else ""
        attempt_count += len(_ATTEMPT_RE.findall(body))
        if _SOLUTION_RE.search(body):
            submitted_solution_count += 1
        if login.startswith("algora-pbc") and ("algora.io/claims/" in body or "[Reward](" in body):
            reward_receipt_count += body.count("algora.io/claims/") or 1

    # A completed reward receipt means this board entry is exhausted or ambiguous.
    # More than one visible attempt, or any already-submitted solution, makes the
    # mission too crowded for the cash-first lane.
    if reward_receipt_count > 0 or attempt_count > 1 or submitted_solution_count > 0:
        return None
    return {
        "attempt_count": attempt_count,
        "submitted_solution_count": submitted_solution_count,
        "reward_receipt_count": reward_receipt_count,
    }


def verify_open_issue(
    opportunity: InternetOpportunity,
    *,
    fetcher: Fetcher | None = None,
) -> InternetOpportunity | None:
    """Return a canonical open and realistically claimable issue, otherwise fail closed."""
    parsed = urlparse(opportunity.source_url)
    match = _ISSUE_RE.match(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not match:
        return None
    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    active_fetcher = fetcher or _default_fetcher
    try:
        payload = json.loads(active_fetcher(api_url).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("state") != "open" or payload.get("pull_request"):
        return None
    canonical_url = str(payload.get("html_url") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not canonical_url or not title:
        return None

    audit = _audit_bounty_comments(opportunity, payload, fetcher=active_fetcher)
    if audit is None:
        return None

    metadata = dict(opportunity.metadata)
    metadata.update(
        {
            "github_state_verified": True,
            "github_api_url": api_url,
            "github_canonical_url": canonical_url,
            "github_updated_at": payload.get("updated_at"),
            "github_bounty_comment_audit": audit,
        }
    )
    evidence = tuple(dict.fromkeys((*opportunity.evidence, api_url, canonical_url)))
    payment_evidence = tuple(dict.fromkeys((*opportunity.payment_evidence, api_url)))
    return replace(
        opportunity,
        source_url=canonical_url,
        title=title,
        description=str(payload.get("body") or opportunity.description)[:4000],
        evidence=evidence,
        payment_evidence=payment_evidence,
        metadata=metadata,
    )


def verify_open_issues(
    opportunities: list[InternetOpportunity],
    *,
    fetcher: Fetcher | None = None,
) -> tuple[list[InternetOpportunity], int]:
    verified: list[InternetOpportunity] = []
    rejected = 0
    for opportunity in opportunities:
        canonical = verify_open_issue(opportunity, fetcher=fetcher)
        if canonical is None:
            rejected += 1
        else:
            verified.append(canonical)
    return verified, rejected
