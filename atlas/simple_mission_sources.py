"""Official public sources for simple, fast freelance missions.

The source is intentionally conservative. It only accepts current remote listings
whose public Freelancer category page exposes an explicit budget range, remaining
time and bounded bid count. Average bids are not treated as payer budget evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]

_BUDGET_RANGE_RE = re.compile(
    r"(?P<symbol>[$€£])\s*(?P<minimum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*-\s*"
    r"(?P=symbol)?\s*(?P<maximum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)"
)
_DAYS_LEFT_RE = re.compile(r"(?P<days>\d+)\s+days?\s+left", re.I)
_BIDS_RE = re.compile(r"(?P<bids>\d+)\s+bids?", re.I)

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
_UNSAFE_TERMS = (
    "fake review",
    "fake testimonial",
    "bulk whatsapp",
    "mass whatsapp",
    "buy followers",
    "account credentials",
    "password",
    "bypass",
    "unauthorized",
    "adult content",
    "gambling",
    "casino",
    "crypto investment",
    "manual only",
    "no automated tools",
    "no automation",
)
_PHYSICAL_TERMS = (
    "on-site",
    "onsite",
    "visit an address",
    "take geotagged photos",
    "in person",
    "local job",
    "must be based in",
    "reserved for candidates based in",
)


@dataclass(frozen=True)
class _Anchor:
    href: str
    text: str
    token_index: int


class _IndexedPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tokens: list[str] = []
        self.anchors: list[_Anchor] = []
        self._href = ""
        self._anchor_tokens: list[str] = []
        self._anchor_start = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._anchor_tokens = []
            self._anchor_start = len(self.tokens)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = " ".join(self._anchor_tokens).strip()
            self.anchors.append(_Anchor(self._href, text, self._anchor_start))
            self._href = ""
            self._anchor_tokens = []

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self.tokens.append(cleaned)
        if self._href:
            self._anchor_tokens.append(cleaned)


class FreelancerPublicJobsSource:
    """Read-only discovery of explicit-budget public Freelancer listings."""

    source_id = "freelancer_public_simple_jobs"
    source_category = "freelance_marketplace"
    allowed_host = "www.freelancer.com"
    category_urls = (
        "https://www.freelancer.com/jobs/data-entry/",
        "https://www.freelancer.com/jobs/web-search/",
        "https://www.freelancer.com/jobs/research-writing/",
        "https://www.freelancer.com/jobs/excel/",
        "https://www.freelancer.com/jobs/translation/",
        "https://www.freelancer.com/jobs/proofreading/",
    )

    def __init__(
        self,
        *,
        category_urls: tuple[str, ...] | None = None,
        maximum_bids: int = 10,
        maximum_budget: float = 1_000.0,
        maximum_results: int = 40,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 3_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.urls = category_urls or self.category_urls
        if not self.urls or maximum_bids < 0 or maximum_budget <= 0 or maximum_results <= 0:
            raise ValueError("source limits must be valid")
        self.maximum_bids = maximum_bids
        self.maximum_budget = maximum_budget
        self.maximum_results = maximum_results
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        opportunities: dict[str, InternetOpportunity] = {}
        errors: list[str] = []
        for page_url in self.urls:
            try:
                payload = self._fetcher(page_url).decode("utf-8")
                for item in self._parse_page(page_url, payload):
                    existing = opportunities.get(item.canonical_url)
                    if existing is None or item.competition < existing.competition:
                        opportunities[item.canonical_url] = item
                    if len(opportunities) >= self.maximum_results:
                        break
            except Exception as exc:
                errors.append(f"{page_url}:{type(exc).__name__}:{exc}")

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
            evidence=tuple(self.urls),
            observed_count=len(rows),
        )

    def _parse_page(self, page_url: str, html: str) -> list[InternetOpportunity]:
        parser = _IndexedPageParser()
        parser.feed(html)
        project_anchors = [
            anchor
            for anchor in parser.anchors
            if "/projects/" in urlparse(urljoin(page_url, anchor.href)).path
            and anchor.text
            and anchor.text.casefold() not in {"bid now", "view project"}
        ]
        rows: list[InternetOpportunity] = []
        seen: set[str] = set()
        for index, anchor in enumerate(project_anchors):
            canonical = urljoin(page_url, anchor.href).split("?", 1)[0].rstrip("/")
            if canonical in seen:
                continue
            seen.add(canonical)
            next_index = (
                project_anchors[index + 1].token_index
                if index + 1 < len(project_anchors)
                else min(len(parser.tokens), anchor.token_index + 90)
            )
            end = min(len(parser.tokens), max(anchor.token_index + 12, next_index), anchor.token_index + 90)
            context = " ".join(parser.tokens[anchor.token_index:end])
            opportunity = self._parse_card(page_url, canonical, anchor.text, context)
            if opportunity is not None:
                rows.append(opportunity)
        return rows

    def _parse_card(
        self,
        page_url: str,
        project_url: str,
        title: str,
        context: str,
    ) -> InternetOpportunity | None:
        budget = _BUDGET_RANGE_RE.search(context)
        days = _DAYS_LEFT_RE.search(context)
        bids = _BIDS_RE.search(context)
        if not budget or not days or not bids:
            return None

        minimum = float(budget.group("minimum").replace(",", ""))
        maximum = float(budget.group("maximum").replace(",", ""))
        days_left = int(days.group("days"))
        bid_count = int(bids.group("bids"))
        if minimum <= 0 or maximum < minimum or maximum > self.maximum_budget:
            return None
        if days_left <= 0 or bid_count > self.maximum_bids:
            return None

        text = f"{title}\n{context}".casefold()
        if any(term in text for term in _UNSAFE_TERMS):
            return None
        if " local " in f" {text} " or any(term in text for term in _PHYSICAL_TERMS):
            return None

        capability = infer_simple_capability(title, context)
        effort = estimate_simple_effort(title, context)
        symbol = budget.group("symbol")
        evidence_excerpt = context[:1_200]
        observed = datetime.now(timezone.utc).isoformat()
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=project_url,
            title=title.strip(),
            description=evidence_excerpt,
            reward_amount=minimum,
            currency=_CURRENCY[symbol],
            reward_verified=True,
            payment_evidence=(page_url, evidence_excerpt),
            required_capabilities=(capability,),
            observed_at=observed,
            deadline=f"{days_left} days left",
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            accessibility=0.86,
            human_dependency=0.22,
            risk=0.20,
            cost=0.10,
            competition=min(1.0, bid_count / 20.0),
            time_to_cash_days=30,
            evidence=(page_url, project_url),
            metadata={
                "official_source": True,
                "platform": "Freelancer.com",
                "source_kind": "public_freelance_listing",
                "budget_min": minimum,
                "budget_max": maximum,
                "budget_currency": _CURRENCY[symbol],
                "active_bids": bid_count,
                "days_left": days_left,
                "estimated_effort_hours": effort,
                "payment_methods": ["Freelancer milestone payment; account payout method selected after award"],
                "submission_mode": "platform_proposal",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "payout_setup_required": False,
                "source_page": page_url,
            },
        )

    def _default_fetcher(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != self.allowed_host:
            raise ValueError("Freelancer source only permits www.freelancer.com")
        request = Request(
            url,
            headers={"Accept": "text/html", "User-Agent": "Louis-OS-Cash-First/1.0"},
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310: fixed host
            payload = response.read(self.maximum_bytes + 1)
        if len(payload) > self.maximum_bytes:
            raise ValueError("response exceeds maximum_bytes")
        return payload


def infer_simple_capability(title: str, description: str = "") -> str:
    text = f"{title}\n{description}".casefold()
    if any(term in text for term in ("lead generation", "web search", "market research", "research list", "contact list", "data collection")):
        return "evidence_research_dossier"
    if any(term in text for term in ("broken link", "dead link", "replace url")):
        return "broken_link_replacement"
    if any(term in text for term in ("spreadsheet", "excel", "csv", "data cleansing", "formula")):
        return "python_data_analysis"
    if any(term in text for term in ("translation", "translator", "translate")):
        return "translation_delivery"
    if any(term in text for term in ("proofreading", "editing", "transcription", "data entry", "copy typing", "word processing")):
        return "structured_document_delivery"
    return "technical_proposal"


def estimate_simple_effort(title: str, description: str = "") -> float:
    text = f"{title}\n{description}".casefold()
    if any(term in text for term in ("lead generation", "web search", "market research", "contact list")):
        return 8.0
    if any(term in text for term in ("proofreading", "editing", "translation", "spreadsheet", "excel")):
        return 8.0
    if any(term in text for term in ("data entry", "copy typing", "transcription")):
        return 12.0
    return 12.0
