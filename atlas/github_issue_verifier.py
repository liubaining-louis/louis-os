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


def verify_open_issue(
    opportunity: InternetOpportunity,
    *,
    fetcher: Fetcher | None = None,
) -> InternetOpportunity | None:
    """Return a canonical open issue opportunity, otherwise fail closed with None."""
    parsed = urlparse(opportunity.source_url)
    match = _ISSUE_RE.match(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not match:
        return None
    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    try:
        payload = json.loads((fetcher or _default_fetcher)(api_url).decode("utf-8"))
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
    metadata = dict(opportunity.metadata)
    metadata.update(
        {
            "github_state_verified": True,
            "github_api_url": api_url,
            "github_canonical_url": canonical_url,
            "github_updated_at": payload.get("updated_at"),
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
