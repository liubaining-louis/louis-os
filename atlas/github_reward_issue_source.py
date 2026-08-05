"""GitHub API discovery for open issues with platform-backed rewards.

This source does not trust issue titles or labels as payment proof. A candidate is
accepted only when an Algora or Opire bot comment exposes both a platform URL and
an explicit positive reward amount. Canonical issue state and bounded competition
are checked before the opportunity enters the market engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
from typing import Callable
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .small_bounty_sources import infer_bounded_capability
from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]
_MONEY_RE = re.compile(
    r"(?:\$\s*(?P<dollars>[0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"(?P<usd>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*USD)",
    re.I,
)
_PLATFORM_LINK_RE = re.compile(
    r"https://(?:algora\.io|(?:app\.)?opire\.dev)/[^\s)\]>'\"]+",
    re.I,
)
_ATTEMPT_RE = re.compile(r"(?im)^\s*/(?:attempt|try)\b|\btrying to solve\b")
_SOLUTION_RE = re.compile(r"(?i)https://github\.com/[^\s)]+/pull/\d+|\bsubmitted (?:a )?(?:fix|solution)\b")
_TRUSTED_BOT_PREFIXES = ("algora", "opire")
_UNSAFE_TERMS = (
    "bypass",
    "credential",
    "password",
    "secret key",
    "api key disclosure",
    "exploit production",
    "unauthorized",
    "fake review",
    "spam",
)


def _amount(match: re.Match[str]) -> float:
    raw = match.group("dollars") or match.group("usd") or "0"
    return float(raw.replace(",", ""))


def _unsafe(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in _UNSAFE_TERMS)


def _default_fetcher(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("GitHub reward source only permits api.github.com")
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
        return response.read(3_000_001)


class GitHubRewardIssueSource:
    """Discover low-competition GitHub issues with trusted reward-bot evidence."""

    source_id = "github_reward_issues"
    source_category = "code_bounty"
    api_root = "https://api.github.com"
    search_queries = (
        'is:issue is:open label:bounty',
        'is:issue is:open label:"💎 Bounty"',
        'is:issue is:open label:reward',
    )

    def __init__(
        self,
        *,
        queries: tuple[str, ...] | None = None,
        maximum_results: int = 40,
        maximum_reward: float = 2_000.0,
        maximum_attempts: int = 1,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.queries = queries or self.search_queries
        if not self.queries or maximum_results <= 0 or maximum_reward <= 0 or maximum_attempts < 0:
            raise ValueError("source limits must be valid")
        self.maximum_results = maximum_results
        self.maximum_reward = maximum_reward
        self.maximum_attempts = maximum_attempts
        self._fetcher = fetcher or _default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        opportunities: dict[str, InternetOpportunity] = {}
        errors: list[str] = []
        evidence: list[str] = []
        for query in self.queries:
            url = f"{self.api_root}/search/issues?q={quote(query)}&sort=updated&order=desc&per_page=50"
            evidence.append(url)
            try:
                payload = json.loads(self._fetcher(url).decode("utf-8"))
                items = payload.get("items") if isinstance(payload, dict) else None
                if not isinstance(items, list):
                    raise ValueError("GitHub issue search returned no items list")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    opportunity = self._parse_issue(item)
                    if opportunity is not None:
                        opportunities[opportunity.canonical_url] = opportunity
                    if len(opportunities) >= self.maximum_results:
                        break
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            if len(opportunities) >= self.maximum_results:
                break

        rows = list(opportunities.values())[: self.maximum_results]
        status = "ok" if rows else "empty"
        if errors and rows:
            status = "partial"
        elif errors and not rows:
            status = "failed"
        return rows, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status=status,
            reason="; ".join(errors[:5]),
            evidence=tuple(evidence),
            observed_count=len(rows),
        )

    def _parse_issue(self, item: dict) -> InternetOpportunity | None:
        if item.get("state") != "open" or item.get("pull_request"):
            return None
        issue_url = str(item.get("html_url") or "").strip()
        api_url = str(item.get("url") or "").strip()
        comments_url = str(item.get("comments_url") or "").strip()
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "")
        if not issue_url or not api_url or not comments_url or not title or _unsafe(f"{title}\n{body}"):
            return None
        if item.get("assignees"):
            return None

        try:
            comments = json.loads(self._fetcher(f"{comments_url}?per_page=100").decode("utf-8"))
        except Exception:
            return None
        if not isinstance(comments, list):
            return None

        reward_amount = 0.0
        payment_comment_url = ""
        platform_url = ""
        payment_excerpt = ""
        attempt_count = 0
        solution_count = 0
        platform = ""

        for comment in comments:
            if not isinstance(comment, dict):
                continue
            comment_body = str(comment.get("body") or "")
            login = str((comment.get("user") or {}).get("login") or "").casefold()
            attempt_count += len(_ATTEMPT_RE.findall(comment_body))
            solution_count += len(_SOLUTION_RE.findall(comment_body))
            if not login.startswith(_TRUSTED_BOT_PREFIXES):
                continue
            link_match = _PLATFORM_LINK_RE.search(comment_body)
            amounts = [_amount(match) for match in _MONEY_RE.finditer(comment_body)]
            if not link_match or not amounts:
                continue
            amount = max(amounts)
            if amount <= reward_amount:
                continue
            reward_amount = amount
            platform_url = link_match.group(0).rstrip(".,")
            payment_comment_url = str(comment.get("html_url") or comments_url)
            payment_excerpt = comment_body[:1_000]
            platform = "Algora" if "algora.io" in platform_url.casefold() else "Opire"

        if (
            reward_amount <= 0
            or reward_amount > self.maximum_reward
            or not platform_url
            or attempt_count > self.maximum_attempts
            or solution_count > 0
        ):
            return None

        capability = infer_bounded_capability(title, body)
        effort = 4.0 if capability != "technical_proposal" else 8.0
        observed_at = datetime.now(timezone.utc).isoformat()
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=issue_url,
            title=title,
            description=body[:4_000] or payment_excerpt,
            reward_amount=round(reward_amount, 2),
            currency="USD",
            reward_verified=True,
            payment_evidence=(payment_comment_url, platform_url, payment_excerpt),
            required_capabilities=(capability,),
            observed_at=observed_at,
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=True,
            accessibility=0.95,
            human_dependency=0.15,
            risk=0.15,
            cost=0.05,
            competition=min(1.0, attempt_count / 5.0),
            time_to_cash_days=21,
            evidence=(api_url, comments_url, payment_comment_url, platform_url),
            metadata={
                "official_source": True,
                "source_kind": "github_platform_reward_issue",
                "platform": platform,
                "status_verified_open": True,
                "active_attempts": attempt_count,
                "submitted_solutions": solution_count,
                "estimated_effort_hours": effort,
                "payment_methods": [f"{platform} platform payout"],
                "payout_setup_required": True,
                "github_api_url": api_url,
            },
        )
