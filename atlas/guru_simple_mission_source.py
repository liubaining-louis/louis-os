"""Fail-closed read-only discovery for small public Guru jobs.

Only current jobs with an explicit bounded rate, low quote count, a future quote
deadline and strong employer payment history are accepted. Public discovery never
creates an account, sends a quote, accepts terms or claims revenue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable, Pattern
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .simple_mission_sources import estimate_simple_effort, infer_simple_capability
from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]

_FIXED_RANGE_RE = re.compile(
    r"Fixed\s+Price\s*\|\s*(?P<symbol>[$€£])\s*(?P<minimum>[0-9][0-9.,]*(?:k)?)\s*-\s*"
    r"(?P<maximum>(?:[$€£])?\s*[0-9][0-9.,]*(?:k)?)",
    re.I,
)
_HOURLY_RANGE_RE = re.compile(
    r"Hourly\s*\|\s*(?P<symbol>[$€£])\s*(?P<minimum>[0-9][0-9.,]*)\s*-\s*"
    r"(?P<maximum>(?:[$€£])?\s*[0-9][0-9.,]*)\s*\|\s*1\s*-\s*10\s+hrs?/wk\s*\|\s*1\s*-\s*4\s+weeks?",
    re.I,
)
_QUOTES_RE = re.compile(r"(?:(?P<count>\d+)\s+Quotes?\s+Received|No\s+Quotes?\s+Received)", re.I)
_DEADLINE_RE = re.compile(r"Send\s+before\s+(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})")
_EMPLOYER_RE = re.compile(r"(?P<spent>[0-9][0-9,]*)\s+Spent\s*\|\s*(?P<payment>[0-9]+(?:\.[0-9]+)?)%", re.I)

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
_ALLOWED_CAPABILITIES = {
    "evidence_research_dossier",
    "python_data_analysis",
    "translation_delivery",
    "structured_document_delivery",
    "broken_link_replacement",
}
_REJECT_TERMS = (
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
    "no ai",
    "no automated tools",
    "no automation",
    "cold calling",
    "telemarketing",
    "commission only",
    "commission-only",
    "paid based on results",
    "tax return",
    "tax services",
    "bookkeeping",
    "accounting services",
    "legal advice",
    "old microsoft ads account",
    "must have old",
    "long-term",
    "long term",
    "full-time",
    "full time",
    "part-time",
    "part time",
    "permanent position",
    "30+ hrs/wk",
    "10-30 hrs/wk",
    "3-6 months",
    "6+ months",
)
_PHYSICAL_OR_SENSITIVE_TERMS = (
    "on-site",
    "onsite",
    "on the ground",
    "on-the-ground",
    "field visit",
    "field verification",
    "site visit",
    "site verification",
    "physical verification",
    "visit an address",
    "visit the address",
    "visit premises",
    "visit the premises",
    "geotagged",
    "in person",
    "must be based in",
    "india-based",
    "personally has an active",
    "native speaker",
    "voice recording",
    "audio recording",
    "using your phone",
    "employment verification",
    "background check",
    "background verification",
    "education verification",
    "criminal background",
    "candidate consent form",
    "contact the hr",
    "former employer",
    "stamped confirmation",
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


class GuruPublicJobsSource:
    """Read public Guru pages and retain only bounded remote digital work."""

    source_id = "guru_public_simple_jobs"
    source_category = "freelance_marketplace"
    allowed_host = "www.guru.com"
    directory_urls = (
        "https://www.guru.com/d/jobs/",
        "https://www.guru.com/d/jobs/pg/2/",
        "https://www.guru.com/d/jobs/pg/3/",
    )

    def __init__(
        self,
        *,
        directory_urls: tuple[str, ...] | None = None,
        maximum_quotes: int = 12,
        maximum_fixed_budget: float = 1_000.0,
        maximum_hourly_rate: float = 50.0,
        minimum_employer_payment_percent: float = 95.0,
        maximum_results: int = 40,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 3_000_000,
        now: datetime | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.urls = directory_urls or self.directory_urls
        if not self.urls or maximum_quotes < 0 or maximum_results <= 0:
            raise ValueError("source limits must be valid")
        self.maximum_quotes = maximum_quotes
        self.maximum_fixed_budget = maximum_fixed_budget
        self.maximum_hourly_rate = maximum_hourly_rate
        self.minimum_employer_payment_percent = minimum_employer_payment_percent
        self.maximum_results = maximum_results
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self.now = now or datetime.now(timezone.utc)
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
        job_anchors = [anchor for anchor in parser.anchors if self._is_job_anchor(page_url, anchor)]
        rows: list[InternetOpportunity] = []
        seen: set[str] = set()
        for index, anchor in enumerate(job_anchors):
            canonical = urljoin(page_url, anchor.href).split("?", 1)[0].split("&", 1)[0].rstrip("/")
            if canonical in seen:
                continue
            seen.add(canonical)

            start = max(0, anchor.token_index - 1)
            if index + 1 < len(job_anchors):
                # The token immediately before the next title is its own posted/quote
                # header. Excluding it prevents evidence from adjacent cards leaking
                # into the current job's budget, competition or employer history.
                end = max(anchor.token_index + 1, job_anchors[index + 1].token_index - 1)
            else:
                end = min(len(parser.tokens), anchor.token_index + 100)
            context = " ".join(parser.tokens[start:end])
            opportunity = self._parse_card(page_url, canonical, anchor.text, context)
            if opportunity is not None:
                rows.append(opportunity)
        return rows

    def _is_job_anchor(self, page_url: str, anchor: _Anchor) -> bool:
        if not anchor.text or anchor.text.casefold() in {"send quote", "find a job"}:
            return False
        parsed = urlparse(urljoin(page_url, anchor.href))
        parts = [part for part in parsed.path.split("/") if part]
        return parsed.hostname == self.allowed_host and len(parts) >= 3 and parts[0] == "jobs"

    def _parse_card(
        self,
        page_url: str,
        job_url: str,
        title: str,
        context: str,
    ) -> InternetOpportunity | None:
        quote_match = _last_match(_QUOTES_RE, context)
        deadline_match = _last_match(_DEADLINE_RE, context)
        employer_match = _last_match(_EMPLOYER_RE, context)
        if not quote_match or not deadline_match or not employer_match:
            return None

        quote_count = int(quote_match.group("count") or 0)
        if quote_count > self.maximum_quotes:
            return None
        deadline = datetime.strptime(
            f"{deadline_match.group('month')} {deadline_match.group('day')} {deadline_match.group('year')}",
            "%b %d %Y",
        ).replace(tzinfo=timezone.utc)
        if deadline.date() < self.now.date():
            return None

        employer_spend = float(employer_match.group("spent").replace(",", ""))
        employer_payment_percent = float(employer_match.group("payment"))
        if employer_spend <= 0 or employer_payment_percent < self.minimum_employer_payment_percent:
            return None

        text = f"{title}\n{context}".casefold()
        if any(term in text for term in _REJECT_TERMS):
            return None
        if any(term in text for term in _PHYSICAL_OR_SENSITIVE_TERMS):
            return None

        capability = infer_simple_capability(title, context)
        if capability not in _ALLOWED_CAPABILITIES:
            return None
        effort = estimate_simple_effort(title, context)

        fixed = _last_match(_FIXED_RANGE_RE, context)
        hourly = _last_match(_HOURLY_RANGE_RE, context)
        budget_kind = ""
        budget_min = 0.0
        budget_max = 0.0
        symbol = ""
        estimated_total_min = 0.0
        if fixed:
            symbol = fixed.group("symbol")
            budget_min = _number(fixed.group("minimum"))
            budget_max = _number(fixed.group("maximum"))
            budget_kind = "fixed_range"
            reward_amount = budget_min
            estimated_total_min = budget_min
            reward_unit = "fixed_total"
            if budget_min <= 0 or budget_max < budget_min or budget_max > self.maximum_fixed_budget:
                return None
        elif hourly:
            symbol = hourly.group("symbol")
            budget_min = _number(hourly.group("minimum"))
            budget_max = _number(hourly.group("maximum"))
            budget_kind = "hourly_range"
            if budget_min <= 0 or budget_max < budget_min or budget_max > self.maximum_hourly_rate:
                return None
            # Keep the externally displayed hourly lower bound as the verified amount.
            # The estimated total remains metadata and is never presented as payer proof.
            reward_amount = budget_min
            estimated_total_min = round(budget_min * effort, 2)
            reward_unit = "per_hour"
        else:
            return None

        excerpt = context[:1_500]
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=job_url,
            title=title.strip(),
            description=excerpt,
            reward_amount=round(reward_amount, 2),
            currency=_CURRENCY[symbol],
            reward_verified=True,
            payment_evidence=(page_url, excerpt, "https://www.guru.com/safepay/"),
            required_capabilities=(capability,),
            observed_at=datetime.now(timezone.utc).isoformat(),
            deadline=deadline.date().isoformat(),
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            accessibility=0.84,
            human_dependency=0.20,
            risk=0.16,
            cost=0.08,
            competition=min(1.0, quote_count / 20.0),
            time_to_cash_days=30,
            evidence=(page_url, job_url, "https://www.guru.com/how-it-works-freelancer/"),
            metadata={
                "official_source": True,
                "platform": "Guru",
                "source_kind": "public_freelance_listing",
                "budget_kind": budget_kind,
                "budget_min": budget_min,
                "budget_max": budget_max,
                "budget_currency": _CURRENCY[symbol],
                "reward_unit": reward_unit,
                "estimated_total_min": estimated_total_min,
                "active_quotes": quote_count,
                "employer_spend": employer_spend,
                "employer_payment_percent": employer_payment_percent,
                "estimated_effort_hours": effort,
                "payment_methods": [
                    "Guru SafePay; PayPal, Payoneer, wire transfer or supported bank transfer after award"
                ],
                "submission_mode": "platform_quote",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "payout_setup_required": False,
                "source_page": page_url,
                "human_action_instructions": [],
            },
        )

    def _default_fetcher(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != self.allowed_host:
            raise ValueError("Guru source only permits www.guru.com")
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


def _last_match(pattern: Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


def _number(value: str) -> float:
    cleaned = value.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip().casefold()
    multiplier = 1_000.0 if cleaned.endswith("k") else 1.0
    if cleaned.endswith("k"):
        cleaned = cleaned[:-1]
    return float(cleaned) * multiplier
