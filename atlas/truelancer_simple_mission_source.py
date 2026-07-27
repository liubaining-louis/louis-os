"""Fail-closed read-only discovery for small public Truelancer projects.

The adapter uses only public official pages. A project is accepted only when the
platform exposes a positive budget, bounded proposal count, recent posting age,
remote-compatible scope, active canonical detail page and credible client payment
history. Discovery never signs up, applies, pays, accepts terms or claims revenue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .automation_compatibility import explicitly_prohibits_automated_delivery
from .simple_mission_sources import estimate_simple_effort, infer_simple_capability
from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]

_FIXED_RE = re.compile(r"Fixed\s+Price\s*\|\s*Posted:\s*(?P<age>.+?)\s+(?P<symbol>[$€£₹])\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
_HOURLY_RE = re.compile(
    r"Hourly\s*\|\s*Posted:\s*(?P<age>.+?)\s+(?P<symbol>[$€£₹])\s*(?P<rate>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*/\s*Hr\s+approx:\s*(?P<hours>[0-9]+(?:\.[0-9]+)?)\s*Hrs?",
    re.I,
)
_PROPOSALS_RE = re.compile(r"(?:(?P<count>[0-9]+)\s+proposals?|Be\s+the\s+first\s+one)", re.I)
_POSTED_DETAIL_RE = re.compile(r"(?:Hourly|Fixed Price)\s+Project\s*\|\s*Posted\s+(?P<age>.+?)(?:\s|$)", re.I)
_DETAIL_HOURLY_RE = re.compile(r"(?P<symbol>[$€£₹])\s*(?P<rate>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*/\s*Hour", re.I)
_DETAIL_FIXED_RE = re.compile(r"(?P<symbol>[$€£₹])\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+(?:Budget|[0-9]+\s+Proposals)", re.I)
_DETAIL_HOURS_RE = re.compile(r"Estimated\s+Hour\s*-\s*(?P<hours>[0-9]+(?:\.[0-9]+)?)\s*hrs?", re.I)
_DETAIL_PROPOSALS_RE = re.compile(r"(?P<count>[0-9]+)\s+Proposals", re.I)
_PROJECTS_PAID_RE = re.compile(r"Projects\s+Paid\s+(?P<count>[0-9]+)", re.I)
_TOTAL_SPENT_RE = re.compile(r"Total\s+Spent\s+(?P<symbol>[$€£₹])?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
_GENERIC_ANCHORS = {"view & apply", "send proposal", "find jobs", "freelance jobs"}
_REJECT_TERMS = (
    "long term",
    "long-term",
    "full time",
    "full-time",
    "part time",
    "part-time",
    "monthly work",
    "ongoing",
    "commission only",
    "commission-only",
    "paid based on results",
    "cold calling",
    "telemarketing",
    "sales expert",
    "appointment setting",
    "social media posting",
    "tiktok posts",
    "facebook ads",
    "google ads",
    "adult content",
    "gambling",
    "casino",
    "crypto investment",
    "security deposit",
    "pay registration fee",
    "whatsapp",
    "telegram",
    "contact outside",
)
_PHYSICAL_OR_SENSITIVE_TERMS = (
    "on-site",
    "onsite",
    "on the ground",
    "on-the-ground",
    "field visit",
    "site visit",
    "physical verification",
    "visit an address",
    "geotagged",
    "in person",
    "must be based in",
    "employment verification",
    "background check",
    "education verification",
    "candidate consent",
    "former employer",
    "stamped confirmation",
    "voice recording",
    "audio recording",
)
_ALLOWED_CAPABILITIES = {
    "evidence_research_dossier",
    "python_data_analysis",
    "translation_delivery",
    "structured_document_delivery",
    "broken_link_replacement",
}


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


@dataclass(frozen=True)
class _ListingCandidate:
    title: str
    url: str
    context: str
    budget_kind: str
    symbol: str
    reward_amount: float
    rate: float
    estimated_hours: float
    proposals: int
    posted_age_hours: float


class TruelancerPublicJobsSource:
    source_id = "truelancer_public_simple_jobs"
    source_category = "freelance_marketplace"
    allowed_host = "www.truelancer.com"
    directory_urls = (
        "https://www.truelancer.com/freelance-jobs?page=1",
        "https://www.truelancer.com/freelance-jobs?page=2",
        "https://www.truelancer.com/freelance-jobs?page=3",
    )
    security_url = "https://www.truelancer.com/freelance-jobs?page=1"

    def __init__(
        self,
        *,
        directory_urls: tuple[str, ...] | None = None,
        maximum_proposals: int = 10,
        maximum_age_hours: float = 168.0,
        maximum_effort_hours: float = 16.0,
        maximum_fixed_budget: float = 1_000.0,
        maximum_hourly_rate: float = 100.0,
        maximum_details: int = 40,
        minimum_client_projects_paid: int = 1,
        minimum_client_total_spent: float = 1.0,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 3_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.urls = directory_urls or self.directory_urls
        if not self.urls or maximum_proposals < 0 or maximum_effort_hours <= 0 or maximum_details <= 0:
            raise ValueError("source limits must be valid")
        self.maximum_proposals = maximum_proposals
        self.maximum_age_hours = maximum_age_hours
        self.maximum_effort_hours = maximum_effort_hours
        self.maximum_fixed_budget = maximum_fixed_budget
        self.maximum_hourly_rate = maximum_hourly_rate
        self.maximum_details = maximum_details
        self.minimum_client_projects_paid = minimum_client_projects_paid
        self.minimum_client_total_spent = minimum_client_total_spent
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        candidates: dict[str, _ListingCandidate] = {}
        errors: list[str] = []
        security_evidence = False
        for page_url in self.urls:
            try:
                html = self._fetcher(page_url).decode("utf-8")
                if "Never pay a security deposit" in html or "Keep all transactions within Truelancer" in html:
                    security_evidence = True
                for candidate in self._parse_listing(page_url, html):
                    candidates.setdefault(candidate.url, candidate)
            except Exception as exc:
                errors.append(f"{page_url}:{type(exc).__name__}:{exc}")

        opportunities: list[InternetOpportunity] = []
        for candidate in list(candidates.values())[: self.maximum_details]:
            try:
                detail_html = self._fetcher(candidate.url).decode("utf-8")
                item = self._validate_detail(candidate, detail_html, security_evidence)
                if item is not None:
                    opportunities.append(item)
            except Exception as exc:
                errors.append(f"{candidate.url}:{type(exc).__name__}:{exc}")

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
            evidence=tuple((*self.urls, self.security_url)),
            observed_count=len(opportunities),
        )

    def _parse_listing(self, page_url: str, html: str) -> list[_ListingCandidate]:
        parser = _IndexedPageParser()
        parser.feed(html)
        anchors = [
            anchor
            for anchor in parser.anchors
            if "/freelance-project/" in urlparse(urljoin(page_url, anchor.href)).path
            and anchor.text.casefold() not in _GENERIC_ANCHORS
        ]
        output: list[_ListingCandidate] = []
        seen: set[str] = set()
        for index, anchor in enumerate(anchors):
            url = urljoin(page_url, anchor.href).split("?", 1)[0].rstrip("/")
            if url in seen:
                continue
            seen.add(url)
            next_index = anchors[index + 1].token_index if index + 1 < len(anchors) else len(parser.tokens)
            context = " ".join(parser.tokens[anchor.token_index : min(next_index, anchor.token_index + 60)])
            proposals_match = _PROPOSALS_RE.search(context)
            if not proposals_match:
                continue
            proposals = int(proposals_match.group("count") or 0)
            fixed = _FIXED_RE.search(context)
            hourly = _HOURLY_RE.search(context)
            if fixed:
                amount = self._amount(fixed.group("amount"))
                effort = estimate_simple_effort(anchor.text, context)
                candidate = _ListingCandidate(
                    title=anchor.text,
                    url=url,
                    context=context[:1_500],
                    budget_kind="fixed_total",
                    symbol=fixed.group("symbol"),
                    reward_amount=amount,
                    rate=0.0,
                    estimated_hours=effort,
                    proposals=proposals,
                    posted_age_hours=self._age_hours(fixed.group("age")),
                )
            elif hourly:
                rate = self._amount(hourly.group("rate"))
                hours = self._amount(hourly.group("hours"))
                candidate = _ListingCandidate(
                    title=anchor.text,
                    url=url,
                    context=context[:1_500],
                    budget_kind="hourly_estimate",
                    symbol=hourly.group("symbol"),
                    reward_amount=rate * hours,
                    rate=rate,
                    estimated_hours=hours,
                    proposals=proposals,
                    posted_age_hours=self._age_hours(hourly.group("age")),
                )
            else:
                continue
            if self._listing_allowed(candidate):
                output.append(candidate)
        return output

    def _listing_allowed(self, item: _ListingCandidate) -> bool:
        if item.reward_amount <= 0 or item.proposals > self.maximum_proposals:
            return False
        if item.posted_age_hours < 0 or item.posted_age_hours > self.maximum_age_hours:
            return False
        if item.estimated_hours <= 0 or item.estimated_hours > self.maximum_effort_hours:
            return False
        if item.budget_kind == "fixed_total" and item.reward_amount > self.maximum_fixed_budget:
            return False
        if item.budget_kind == "hourly_estimate" and item.rate > self.maximum_hourly_rate:
            return False
        text = f"{item.title}\n{item.context}".casefold()
        if any(term in text for term in _REJECT_TERMS):
            return False
        if any(term in text for term in _PHYSICAL_OR_SENSITIVE_TERMS):
            return False
        capability = infer_simple_capability(item.title, item.context)
        if capability not in _ALLOWED_CAPABILITIES:
            return False
        probe = {"title": item.title, "description": item.context, "payment_evidence": []}
        return not explicitly_prohibits_automated_delivery(probe)

    def _validate_detail(
        self,
        candidate: _ListingCandidate,
        html: str,
        security_evidence: bool,
    ) -> InternetOpportunity | None:
        parser = _IndexedPageParser()
        parser.feed(html)
        text = " ".join(parser.tokens)
        if not re.search(r"\bActive\s+Status\b", text, re.I):
            return None
        if explicitly_prohibits_automated_delivery({"title": candidate.title, "description": text}):
            return None
        lowered = text.casefold()
        if any(term in lowered for term in _REJECT_TERMS) or any(term in lowered for term in _PHYSICAL_OR_SENSITIVE_TERMS):
            return None

        proposals_match = _DETAIL_PROPOSALS_RE.search(text)
        proposals = int(proposals_match.group("count")) if proposals_match else candidate.proposals
        if proposals > self.maximum_proposals:
            return None
        projects_paid_match = _PROJECTS_PAID_RE.search(text)
        spent_match = _TOTAL_SPENT_RE.search(text)
        projects_paid = int(projects_paid_match.group("count")) if projects_paid_match else 0
        total_spent = self._amount(spent_match.group("amount")) if spent_match else 0.0
        if projects_paid < self.minimum_client_projects_paid and total_spent < self.minimum_client_total_spent:
            return None

        effort = candidate.estimated_hours
        hours_match = _DETAIL_HOURS_RE.search(text)
        if hours_match:
            effort = self._amount(hours_match.group("hours"))
        if effort <= 0 or effort > self.maximum_effort_hours:
            return None

        reward = candidate.reward_amount
        rate = candidate.rate
        detail_hourly = _DETAIL_HOURLY_RE.search(text)
        if detail_hourly:
            rate = self._amount(detail_hourly.group("rate"))
            reward = rate * effort
        elif candidate.budget_kind == "fixed_total":
            detail_fixed = _DETAIL_FIXED_RE.search(text)
            if detail_fixed:
                reward = self._amount(detail_fixed.group("amount"))
        if reward <= 0:
            return None

        capability = infer_simple_capability(candidate.title, f"{candidate.context}\n{text}")
        if capability not in _ALLOWED_CAPABILITIES:
            return None
        currency = _CURRENCY[candidate.symbol]
        observed = datetime.now(timezone.utc).isoformat()
        payment_note = (
            "Truelancer platform payment only; never pay a security deposit and keep all transactions within Truelancer"
        )
        evidence_excerpt = f"{candidate.context}\n{text[:2_000]}"
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=candidate.url,
            title=candidate.title,
            description=evidence_excerpt[:2_800],
            reward_amount=round(reward, 2),
            currency=currency,
            reward_verified=True,
            payment_evidence=(self.security_url, candidate.url, evidence_excerpt[:1_500]),
            required_capabilities=(capability,),
            observed_at=observed,
            deadline="recent public listing",
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            accessibility=0.80,
            human_dependency=0.24,
            risk=0.24,
            cost=0.10,
            competition=min(1.0, proposals / 20.0),
            time_to_cash_days=30,
            evidence=(self.security_url, candidate.url),
            metadata={
                "official_source": True,
                "platform": "Truelancer",
                "source_kind": "public_freelance_listing",
                "budget_kind": candidate.budget_kind,
                "budget_currency": currency,
                "verified_reward_total": round(reward, 2),
                "hourly_rate": round(rate, 2) if rate else None,
                "estimated_effort_hours": round(effort, 2),
                "active_proposals": proposals,
                "posted_age_hours": round(candidate.posted_age_hours, 2),
                "client_projects_paid": projects_paid,
                "client_total_spent": round(total_spent, 2),
                "payment_methods": [payment_note],
                "submission_mode": "platform_proposal",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "payout_setup_required": False,
                "platform_gate_instruction": (
                    "Authorize use of a truthful Truelancer account and review/accept the platform terms so Louis OS can submit the prepared proposal. Keep all payment on-platform; never pay a security deposit."
                ),
            },
        )

    @staticmethod
    def _amount(value: str) -> float:
        return float(value.replace(",", "").strip())

    @staticmethod
    def _age_hours(value: str) -> float:
        text = value.strip().casefold()
        if any(term in text for term in ("minute", "minutes")):
            match = re.search(r"([0-9]+)", text)
            return (float(match.group(1)) / 60.0) if match else 0.5
        if any(term in text for term in ("hour", "hours")):
            match = re.search(r"([0-9]+)", text)
            return float(match.group(1)) if match else 1.0
        if text in {"a day ago", "1 day ago", "a day"}:
            return 24.0
        if any(term in text for term in ("day", "days")):
            match = re.search(r"([0-9]+)", text)
            return float(match.group(1)) * 24.0 if match else 24.0
        if any(term in text for term in ("month", "months", "year", "years")):
            return 10_000.0
        return -1.0

    def _default_fetcher(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != self.allowed_host:
            raise ValueError("Truelancer source only permits www.truelancer.com")
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": "Mozilla/5.0 (compatible; Louis-OS-Cash-First/1.0; +https://github.com)",
            },
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310: host allowlisted
            payload = response.read(self.maximum_bytes + 1)
        if len(payload) > self.maximum_bytes:
            raise ValueError("response exceeds maximum_bytes")
        return payload
