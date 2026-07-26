"""Official public small-bounty sources for the cash-first market lane.

The adapters are deliberately read-only and fail closed. A page can become a paid
opportunity only when the platform itself exposes a positive available reward, an
open canonical GitHub issue and bounded competition. Platform pages are evidence;
issue-title amounts alone are never accepted as payment proof.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]
_GITHUB_ISSUE_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/issues/(?P<number>\d+)"
)
_MONEY_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
_UNSAFE_TERMS = (
    "system prompt",
    "hidden prompt",
    "generation context",
    "boot context",
    "secret key",
    "api key disclosure",
    "credential disclosure",
    "password disclosure",
    "exfiltrate",
    "bypass access",
    "star the repository",
    "follow the account",
    "create another issue",
    "find bugs in this fork",
)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._anchor_chunks: list[str] = []
        self._recent: deque[str] = deque(maxlen=18)
        self.anchor_contexts: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._anchor_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._href:
            return
        anchor = " ".join(self._anchor_chunks).strip()
        context = " ".join((*self._recent, anchor)).strip()
        self.links.append((self._href, anchor))
        self.anchor_contexts.append((self._href, anchor, context))
        self._href = ""
        self._anchor_chunks = []

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self.chunks.append(cleaned)
        self._recent.append(cleaned)
        if self._href:
            self._anchor_chunks.append(cleaned)

    @property
    def text(self) -> str:
        return " ".join(self.chunks)


def _amount(value: str) -> float:
    return float(value.replace(",", ""))


def _unsafe(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in _UNSAFE_TERMS)


def infer_bounded_capability(title: str, description: str = "") -> str:
    text = f"{title}\n{description}".casefold()
    if any(term in text for term in ("broken link", "dead link", "update url", "replace url")):
        return "broken_link_replacement"
    if any(
        term in text
        for term in (
            "typo",
            "wording",
            "header text",
            "readme",
            "documentation",
            " docs ",
            "translate",
            "translation",
            "add french",
        )
    ):
        return "deterministic_text_replacement"
    if any(term in text for term in ("expected literal", "test expectation", "assertion value", "fixture value")):
        return "simple_test_expectation_replacement"
    if any(term in text for term in ("configuration scalar", "config value", "environment value", "version constant")):
        return "configuration_scalar_replacement"
    return "technical_proposal"


def _fetch_https(url: str, allowed_hosts: set[str], timeout: float, maximum_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("request host is not allowlisted")
    request = Request(
        url,
        headers={"Accept": "text/html", "User-Agent": "Louis-OS-Cash-First/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310: hosts are allowlisted
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("response exceeds maximum_bytes")
    return payload


class OpirePublicSource:
    source_id = "opire_public_bounties"
    source_category = "code_bounty"
    home_url = "https://app.opire.dev/home"
    allowed_host = "app.opire.dev"

    def __init__(
        self,
        *,
        maximum_details: int = 40,
        maximum_reward: float = 2_000.0,
        maximum_solvers: int = 5,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 2_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        if min(maximum_details, maximum_solvers, maximum_bytes) <= 0 or maximum_reward <= 0 or timeout_seconds <= 0:
            raise ValueError("source limits must be positive")
        self.maximum_details = maximum_details
        self.maximum_reward = maximum_reward
        self.maximum_solvers = maximum_solvers
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        try:
            homepage = self._fetcher(self.home_url)
            parser = _PageParser()
            parser.feed(homepage.decode("utf-8"))
            detail_urls: list[str] = []
            for href, _ in parser.links:
                absolute = urljoin(self.home_url, href)
                parsed = urlparse(absolute)
                if parsed.hostname == self.allowed_host and parsed.path.startswith("/issues/"):
                    canonical = f"https://{self.allowed_host}{parsed.path.rstrip('/')}"
                    if canonical not in detail_urls:
                        detail_urls.append(canonical)
        except Exception as exc:
            return [], self._state("failed", f"{type(exc).__name__}: {exc}", 0)

        opportunities: list[InternetOpportunity] = []
        errors: list[str] = []
        for detail_url in detail_urls[: self.maximum_details]:
            try:
                opportunity = self._parse_detail(detail_url, self._fetcher(detail_url).decode("utf-8"))
                if opportunity is not None:
                    opportunities.append(opportunity)
            except Exception as exc:
                errors.append(f"{detail_url}:{type(exc).__name__}:{exc}")
        status = "ok" if opportunities else "empty"
        if errors and opportunities:
            status = "partial"
        elif errors and not opportunities:
            status = "failed"
        return opportunities, self._state(status, "; ".join(errors[:5]), len(opportunities))

    def _parse_detail(self, detail_url: str, html: str) -> InternetOpportunity | None:
        parser = _PageParser()
        parser.feed(html)
        text = parser.text
        issue_match = _GITHUB_ISSUE_RE.search(text)
        heading = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+bounty for\s+(.+?)\s+Earn up to", text, re.I)
        status = re.search(r"Status:\s*(Open|Closed)\.?", text, re.I)
        available = re.search(r"(\d+)\s+available rewards?", text, re.I)
        if not issue_match or not heading or not status or status.group(1).casefold() != "open":
            return None
        available_count = int(available.group(1)) if available else 0
        if available_count <= 0:
            return None
        available_amounts = [
            _amount(value)
            for value in re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+reward,\s+status Available", text, re.I)
        ]
        reward = sum(available_amounts) if available_amounts else _amount(heading.group(1))
        solver_match = re.search(r"(\d+)\s+solvers? are trying", text, re.I)
        claim_match = re.search(r"(\d+)\s+solvers? have claimed", text, re.I)
        solvers = max(int(solver_match.group(1)) if solver_match else 0, int(claim_match.group(1)) if claim_match else 0)
        title = heading.group(2).strip()
        if reward <= 0 or reward > self.maximum_reward or solvers > self.maximum_solvers or _unsafe(title):
            return None
        issue_url = issue_match.group(0)
        capability = infer_bounded_capability(title, text)
        excerpt_start = max(0, text.find(title) - 50)
        excerpt = text[excerpt_start : excerpt_start + 620]
        effort = 4.0 if capability != "technical_proposal" else 8.0
        now = datetime.now(timezone.utc).isoformat()
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=issue_url,
            title=title,
            description=excerpt,
            reward_amount=round(reward, 2),
            currency="USD",
            reward_verified=True,
            payment_evidence=(detail_url, excerpt),
            required_capabilities=(capability,),
            observed_at=now,
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=True,
            accessibility=0.90,
            human_dependency=0.20,
            risk=0.18,
            cost=0.05,
            competition=min(1.0, solvers / 10.0),
            time_to_cash_days=21,
            evidence=(self.home_url, detail_url, issue_url),
            metadata={
                "official_source": True,
                "source_kind": "public_bounty_platform",
                "platform": "Opire",
                "platform_detail_url": detail_url,
                "available_reward_count": available_count,
                "active_solvers": solvers,
                "estimated_effort_hours": effort,
                "payment_methods": ["Stripe payout via Opire"],
                "payout_setup_required": True,
            },
        )

    def _state(self, status: str, reason: str, count: int) -> SourceState:
        return SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status=status,
            reason=reason,
            evidence=(self.home_url,),
            observed_count=count,
        )

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_https(url, {self.allowed_host}, self.timeout_seconds, self.maximum_bytes)


class AlgoraPublicSource:
    source_id = "algora_public_bounties"
    source_category = "code_bounty"
    allowed_host = "algora.io"
    reviewed_handles = (
        "cal",
        "projectdiscovery",
        "revertinc",
        "Dokploy",
        "comet-ml",
        "antinomyhq",
        "daytonaio",
        "cloudgakkai",
        "aqualinkorg",
        "arakoodev",
    )

    def __init__(
        self,
        *,
        handles: tuple[str, ...] | None = None,
        maximum_reward: float = 2_000.0,
        maximum_claims: int = 5,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 2_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.handles = handles or self.reviewed_handles
        if not self.handles or maximum_reward <= 0 or maximum_claims <= 0 or timeout_seconds <= 0 or maximum_bytes <= 0:
            raise ValueError("source limits must be positive")
        self.maximum_reward = maximum_reward
        self.maximum_claims = maximum_claims
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        grouped: dict[str, InternetOpportunity] = {}
        errors: list[str] = []
        boards: list[str] = []
        for handle in self.handles:
            board_url = f"https://{self.allowed_host}/{handle}/bounties?status=open"
            boards.append(board_url)
            try:
                for opportunity in self._parse_board(board_url, self._fetcher(board_url).decode("utf-8")):
                    existing = grouped.get(opportunity.canonical_url)
                    if existing is None or opportunity.reward_amount > existing.reward_amount:
                        grouped[opportunity.canonical_url] = opportunity
            except Exception as exc:
                errors.append(f"{board_url}:{type(exc).__name__}:{exc}")
        opportunities = list(grouped.values())
        status = "ok" if opportunities else "empty"
        if errors and opportunities:
            status = "partial"
        elif errors and not opportunities:
            status = "failed"
        return opportunities, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status=status,
            reason="; ".join(errors[:5]),
            evidence=tuple(boards),
            observed_count=len(opportunities),
        )

    def _parse_board(self, board_url: str, html: str) -> list[InternetOpportunity]:
        parser = _PageParser()
        parser.feed(html)
        full_text = parser.text
        output: list[InternetOpportunity] = []
        seen: set[tuple[str, float]] = set()
        for href, anchor, context in parser.anchor_contexts:
            absolute = urljoin(board_url, href)
            issue_match = _GITHUB_ISSUE_RE.search(absolute)
            if not issue_match:
                continue
            anchor_text = anchor.strip()
            location = full_text.find(anchor_text) if anchor_text else -1
            window = full_text[max(0, location - 180) : location + 520] if location >= 0 else context
            amounts = [_amount(value) for value in _MONEY_RE.findall(window)]
            if not amounts:
                continue
            reward = amounts[-1] if location >= 0 else amounts[0]
            claims_match = re.search(r"(\d+)\s+claims?", window, re.I)
            claims = int(claims_match.group(1)) if claims_match else 0
            title_match = re.search(r"[A-Za-z0-9_.-]+#\d+\s+(.+?)(?:\s+\d+\s+(?:days?|months?|years?) ago|\s+\d+\s+claims?|$)", window, re.I)
            title = title_match.group(1).strip() if title_match else anchor_text
            key = (issue_match.group(0), reward)
            if key in seen:
                continue
            seen.add(key)
            if reward <= 0 or reward > self.maximum_reward or claims > self.maximum_claims or not title or _unsafe(title):
                continue
            capability = infer_bounded_capability(title, window)
            effort = 4.0 if capability != "technical_proposal" else 8.0
            excerpt = window[:620]
            output.append(
                InternetOpportunity(
                    source_id=self.source_id,
                    source_category=self.source_category,
                    source_url=issue_match.group(0),
                    title=title,
                    description=excerpt,
                    reward_amount=round(reward, 2),
                    currency="USD",
                    reward_verified=True,
                    payment_evidence=(board_url, excerpt),
                    required_capabilities=(capability,),
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    account_required=True,
                    terms_required=True,
                    identity_or_kyc_required=True,
                    accessibility=0.90,
                    human_dependency=0.18,
                    risk=0.18,
                    cost=0.05,
                    competition=min(1.0, claims / 10.0),
                    time_to_cash_days=21,
                    evidence=(board_url, issue_match.group(0)),
                    metadata={
                        "official_source": True,
                        "source_kind": "public_bounty_platform",
                        "platform": "Algora",
                        "active_claims": claims,
                        "estimated_effort_hours": effort,
                        "payment_methods": ["Algora platform payout"],
                        "payout_setup_required": True,
                    },
                )
            )
        return output

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_https(url, {self.allowed_host}, self.timeout_seconds, self.maximum_bytes)
