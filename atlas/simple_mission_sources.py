"""Official public sources for simple, fast freelance missions.

The adapters are deliberately conservative. They only accept current remote listings
whose official public pages expose an explicit payer budget, a live deadline and
bounded competition. Average bids, broad price categories and marketing claims are
never treated as payment evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]

_BUDGET_RANGE_RE = re.compile(
    r"(?P<symbol>[$€£₹])\s*(?P<minimum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*-\s*"
    r"(?P=symbol)?\s*(?P<maximum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)"
)
_DAYS_LEFT_RE = re.compile(r"(?P<days>\d+)\s+days?\s+left", re.I)
_ENDS_IN_RE = re.compile(r"ends\s+in\s+(?P<days>\d+)\s+days?", re.I)
_BIDS_RE = re.compile(r"(?P<bids>\d+)\s+bids?", re.I)
_PROPOSALS_RE = re.compile(r"(?P<bids>\d+)\s+proposals?", re.I)
_GURU_QUOTES_RE = re.compile(r"(?:(?P<quotes>\d+)\s+Quotes? Received|No Quotes Received)", re.I)
_GURU_DEADLINE_RE = re.compile(r"Send before\s+(?P<deadline>[A-Za-z]{3}\s+\d{1,2},\s+\d{4})", re.I)
_GURU_FIXED_RANGE_RE = re.compile(
    r"Fixed Price\s*\|\s*(?P<symbol>[$€£])\s*(?P<minimum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*-\s*"
    r"(?P=symbol)?\s*(?P<maximum>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.I,
)
_GURU_EXACT_BUDGET_RE = re.compile(
    r"(?:target\s+fixed\s+budget|fixed\s+budget|total\s+budget)\s*:\s*"
    r"(?:(?P<code>USD|EUR|GBP)\s*)?(?P<symbol>[$€£])?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.I,
)
_GURU_SPEND_RE = re.compile(
    r"(?P<spend>[0-9][0-9,]*)\s+Spent\s*\|\s*(?P<payment>[0-9]+(?:\.[0-9]+)?)%",
    re.I,
)
_GURU_JOB_PATH_RE = re.compile(r"^/jobs/[^/]+/\d+/?$", re.I)

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
# maximum_budget is expressed in major USD/EUR/GBP-sized units. INR amounts
# need a conservative magnitude adjustment before applying the same scope guard.
_FREELANCER_BUDGET_LIMIT_MULTIPLIER = {"$": 1.0, "€": 1.0, "£": 1.0, "₹": 100.0}
_CODE_CURRENCY = {"USD": "USD", "EUR": "EUR", "GBP": "GBP"}
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
    "on the ground",
    "on-the-ground",
    "field visit",
    "field verification",
    "site visit",
    "site verification",
    "physical verification",
    "visit an address",
    "visit the address",
    "visit institution",
    "visit the institution",
    "visit premises",
    "visit the premises",
    "take geotagged photos",
    "geotagged photo",
    "in person",
    "local job",
    "must be based in",
    "reserved for candidates based in",
    "personally has an active",
    "physical product",
    "product photographer",
    "photography of the actual",
)
_SENSITIVE_VERIFICATION_TERMS = (
    "employment verification",
    "previous employment verification",
    "background check",
    "background verification",
    "education verification",
    "criminal background",
    "candidate consent form",
    "candidate’s consent form",
    "candidate's consent form",
    "contact the hr",
    "former employer",
    "stamped confirmation",
)
_LONG_OR_SPECIALIST_TERMS = (
    "tax return",
    "tax returns",
    "bookkeeping",
    "quickbooks",
    "cold calling",
    "telemarketing",
    "commission only",
    "commission-only",
    "6+ months",
    "3-6 months",
    "long-term",
    "long term",
    "full-time",
    "full time",
    "old microsoft ads account",
    "must have old",
    "voice recording",
    "manual score preparation",
    "legal advice",
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


def _is_disallowed(title: str, context: str) -> bool:
    text = f"{title}\n{context}".casefold()
    return (
        any(term in text for term in _UNSAFE_TERMS)
        or " local " in f" {text} "
        or any(term in text for term in _PHYSICAL_TERMS)
        or any(term in text for term in _SENSITIVE_VERIFICATION_TERMS)
        or any(term in text for term in _LONG_OR_SPECIALIST_TERMS)
    )


def _fetch_public_html(
    url: str,
    *,
    allowed_host: str,
    timeout_seconds: float,
    maximum_bytes: int,
) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise ValueError(f"source only permits {allowed_host}")
    request = Request(
        url,
        headers={"Accept": "text/html", "User-Agent": "Louis-OS-Cash-First/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: fixed host
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("response exceeds maximum_bytes")
    return payload


class FreelancerPublicJobsSource:
    """Read-only discovery of explicit-budget public Freelancer listings."""

    source_id = "freelancer_public_simple_jobs"
    source_category = "freelance_marketplace"
    allowed_host = "www.freelancer.com"
    category_urls = (
        "https://www.freelancer.com/jobs/data-entry/",
        "https://www.freelancer.com/jobs/data-processing/",
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
        maximum_detail_checks: int = 5,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 3_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.urls = category_urls or self.category_urls
        if (
            not self.urls
            or maximum_bids < 0
            or maximum_budget <= 0
            or maximum_results <= 0
            or maximum_detail_checks <= 0
        ):
            raise ValueError("source limits must be valid")
        self.maximum_bids = maximum_bids
        self.maximum_budget = maximum_budget
        self.maximum_results = maximum_results
        self.maximum_detail_checks = maximum_detail_checks
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
        detail_checks = 0
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
            if opportunity is None and detail_checks < self.maximum_detail_checks:
                gate = self._detail_gate(anchor.text, context)
                if gate is not None:
                    detail_checks += 1
                    try:
                        detail_html = self._fetcher(canonical).decode("utf-8")
                        opportunity = self._parse_detail_page(
                            page_url,
                            canonical,
                            anchor.text,
                            detail_html,
                            category_bid_count=gate[1],
                        )
                    except Exception:
                        # A detail-page failure never invalidates the remaining
                        # public category scan and never makes average bids evidence.
                        opportunity = None
            if opportunity is not None:
                rows.append(opportunity)
        return rows

    def _detail_gate(self, title: str, context: str) -> tuple[int, int] | None:
        days = _DAYS_LEFT_RE.search(context)
        bids = _BIDS_RE.search(context)
        if not days or not bids or _is_disallowed(title, context):
            return None
        days_left = int(days.group("days"))
        bid_count = int(bids.group("bids"))
        if days_left <= 0 or bid_count > self.maximum_bids:
            return None
        return days_left, bid_count

    def _parse_detail_page(
        self,
        category_url: str,
        project_url: str,
        title: str,
        html: str,
        *,
        category_bid_count: int,
    ) -> InternetOpportunity | None:
        parser = _IndexedPageParser()
        parser.feed(html)
        title_folded = title.casefold()
        start = next(
            (index for index, token in enumerate(parser.tokens) if title_folded in token.casefold()),
            0,
        )
        status_tokens = parser.tokens[start : start + 45]
        status_context = " ".join(status_tokens)
        context = " ".join(parser.tokens[start : start + 180])
        normalized_statuses = {token.strip().casefold() for token in status_tokens}
        if (
            not normalized_statuses.intersection({"open", "open for bidding"})
            or "closed" in normalized_statuses
            or _is_disallowed(title, context)
        ):
            return None

        budget = _BUDGET_RANGE_RE.search(status_context)
        days = _DAYS_LEFT_RE.search(status_context) or _ENDS_IN_RE.search(status_context)
        proposals = _PROPOSALS_RE.search(context)
        if not budget or not days or not proposals:
            return None

        minimum = float(budget.group("minimum").replace(",", ""))
        maximum = float(budget.group("maximum").replace(",", ""))
        days_left = int(days.group("days"))
        bid_count = int(proposals.group("bids"))
        if (
            minimum <= 0
            or maximum < minimum
            or maximum > self.maximum_budget * _FREELANCER_BUDGET_LIMIT_MULTIPLIER[budget.group("symbol")] * _FREELANCER_BUDGET_LIMIT_MULTIPLIER[budget.group("symbol")]
            or days_left <= 0
            or bid_count > self.maximum_bids
        ):
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
            payment_evidence=(project_url, evidence_excerpt),
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
            evidence=(category_url, project_url),
            metadata={
                "official_source": True,
                "platform": "Freelancer.com",
                "source_kind": "public_freelance_listing",
                "budget_min": minimum,
                "budget_max": maximum,
                "budget_currency": _CURRENCY[symbol],
                "active_bids": bid_count,
                "category_active_bids": category_bid_count,
                "days_left": days_left,
                "estimated_effort_hours": effort,
                "payment_methods": ["Freelancer milestone payment; account payout method selected after award"],
                "submission_mode": "platform_proposal",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "payout_setup_required": False,
                "source_page": category_url,
                "detail_page_verified": True,
            },
        )

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
        if days_left <= 0 or bid_count > self.maximum_bids or _is_disallowed(title, context):
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
        return _fetch_public_html(
            url,
            allowed_host=self.allowed_host,
            timeout_seconds=self.timeout_seconds,
            maximum_bytes=self.maximum_bytes,
        )


class GuruPublicJobsSource:
    """Read-only discovery of explicit-budget jobs from Guru's public directory."""

    source_id = "guru_public_simple_jobs"
    source_category = "freelance_marketplace"
    allowed_host = "www.guru.com"
    jobs_url = "https://www.guru.com/d/jobs/"

    def __init__(
        self,
        *,
        jobs_url: str | None = None,
        maximum_quotes: int = 10,
        maximum_budget: float = 1_000.0,
        minimum_payment_percentage: float = 90.0,
        maximum_results: int = 40,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 3_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.url = jobs_url or self.jobs_url
        if maximum_quotes < 0 or maximum_budget <= 0 or maximum_results <= 0:
            raise ValueError("source limits must be valid")
        self.maximum_quotes = maximum_quotes
        self.maximum_budget = maximum_budget
        self.minimum_payment_percentage = minimum_payment_percentage
        self.maximum_results = maximum_results
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        try:
            html = self._fetcher(self.url).decode("utf-8")
            rows = self._parse_page(self.url, html)[: self.maximum_results]
            status = "ok" if rows else "empty"
            reason = ""
        except Exception as exc:
            rows = []
            status = "failed"
            reason = f"{type(exc).__name__}: {exc}"
        return rows, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status=status,
            reason=reason,
            evidence=(self.url,),
            observed_count=len(rows),
        )

    def _parse_page(self, page_url: str, html: str) -> list[InternetOpportunity]:
        parser = _IndexedPageParser()
        parser.feed(html)
        job_anchors: list[_Anchor] = []
        for anchor in parser.anchors:
            absolute = unquote(urljoin(page_url, anchor.href)).split("&", 1)[0].split("?", 1)[0]
            if not anchor.text or anchor.text.casefold() in {"send quote", "find a job"}:
                continue
            if _GURU_JOB_PATH_RE.match(urlparse(absolute).path):
                job_anchors.append(anchor)

        rows: list[InternetOpportunity] = []
        seen: set[str] = set()
        for index, anchor in enumerate(job_anchors):
            canonical = unquote(urljoin(page_url, anchor.href)).split("&", 1)[0].split("?", 1)[0].rstrip("/")
            if canonical in seen:
                continue
            seen.add(canonical)
            next_index = (
                job_anchors[index + 1].token_index
                if index + 1 < len(job_anchors)
                else min(len(parser.tokens), anchor.token_index + 100)
            )
            start = max(0, anchor.token_index - 5)
            end = min(len(parser.tokens), max(anchor.token_index + 14, next_index), anchor.token_index + 100)
            context = " ".join(parser.tokens[start:end])
            item = self._parse_card(page_url, canonical, anchor.text, context)
            if item is not None:
                rows.append(item)
        return rows

    def _parse_card(
        self,
        page_url: str,
        job_url: str,
        title: str,
        context: str,
    ) -> InternetOpportunity | None:
        quotes_match = _GURU_QUOTES_RE.search(context)
        deadline_match = _GURU_DEADLINE_RE.search(context)
        if not quotes_match or not deadline_match or _is_disallowed(title, context):
            return None

        quote_count = int(quotes_match.group("quotes") or 0)
        if quote_count > self.maximum_quotes:
            return None
        try:
            deadline_dt = datetime.strptime(deadline_match.group("deadline"), "%b %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        now = datetime.now(timezone.utc)
        if deadline_dt.date() < now.date():
            return None
        days_left = max(1, (deadline_dt.date() - now.date()).days)

        range_match = _GURU_FIXED_RANGE_RE.search(context)
        exact_match = _GURU_EXACT_BUDGET_RE.search(context)
        if range_match:
            symbol = range_match.group("symbol")
            minimum = float(range_match.group("minimum").replace(",", ""))
            maximum = float(range_match.group("maximum").replace(",", ""))
            currency = _CURRENCY[symbol]
        elif exact_match:
            minimum = maximum = float(exact_match.group("amount").replace(",", ""))
            symbol = exact_match.group("symbol")
            code = (exact_match.group("code") or "").upper()
            currency = _CURRENCY.get(symbol or "") or _CODE_CURRENCY.get(code)
            if not currency:
                return None
        else:
            return None
        if minimum <= 0 or maximum < minimum or maximum > self.maximum_budget:
            return None

        spend_match = _GURU_SPEND_RE.search(context)
        employer_spend = float(spend_match.group("spend").replace(",", "")) if spend_match else 0.0
        payment_percentage = float(spend_match.group("payment")) if spend_match else 0.0
        if spend_match and payment_percentage < self.minimum_payment_percentage:
            return None

        capability = infer_simple_capability(title, context)
        effort = estimate_simple_effort(title, context)
        excerpt = context[:1_400]
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=job_url,
            title=title.strip(),
            description=excerpt,
            reward_amount=minimum,
            currency=currency,
            reward_verified=True,
            payment_evidence=(page_url, excerpt, "https://www.guru.com/safepay/"),
            required_capabilities=(capability,),
            observed_at=now.isoformat(),
            deadline=deadline_match.group("deadline"),
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            accessibility=0.84 if spend_match else 0.70,
            human_dependency=0.22,
            risk=0.18 if payment_percentage >= 95.0 else 0.25,
            cost=0.10,
            competition=min(1.0, quote_count / 20.0),
            time_to_cash_days=min(30, max(14, days_left + 7)),
            evidence=(page_url, job_url, "https://www.guru.com/how-it-works-freelancer/"),
            metadata={
                "official_source": True,
                "platform": "Guru",
                "source_kind": "public_freelance_listing",
                "budget_min": minimum,
                "budget_max": maximum,
                "budget_currency": currency,
                "active_bids": quote_count,
                "days_left": days_left,
                "employer_spend": employer_spend,
                "employer_payment_percentage": payment_percentage,
                "estimated_effort_hours": effort,
                "payment_methods": [
                    "Guru SafePay; withdrawal by non-U.S. bank account, PayPal or wire transfer after payment"
                ],
                "submission_mode": "platform_quote",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "payout_setup_required": False,
                "source_page": page_url,
            },
        )

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_public_html(
            url,
            allowed_host=self.allowed_host,
            timeout_seconds=self.timeout_seconds,
            maximum_bytes=self.maximum_bytes,
        )


def infer_simple_capability(title: str, description: str = "") -> str:
    text = f"{title}\n{description}".casefold()
    if any(
        term in text
        for term in (
            "lead generation",
            "lead generator",
            "web search",
            "market research",
            "research list",
            "contact list",
            "data collection",
            "data research",
            "company research",
        )
    ):
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


_SMALL_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_PAGE_NUMBER = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})"
_PAGE_RANGE_RE = re.compile(
    rf"\b(?:between\s+({_PAGE_NUMBER})\s+and\s+({_PAGE_NUMBER})|"
    rf"({_PAGE_NUMBER})\s*(?:-|to)\s*({_PAGE_NUMBER}))\s+pages?\b",
    re.I,
)
_PAGE_COUNT_RE = re.compile(rf"\b({_PAGE_NUMBER})\s+pages?\b", re.I)


def _page_count(token: str) -> int:
    return _SMALL_NUMBER_WORDS.get(token.casefold(), int(token) if token.isdigit() else 0)


def _explicit_plain_text_effort(text: str) -> float | None:
    """Estimate only a publicly evidenced, bounded plain-text micro-scope."""
    if not any(term in text for term in ("pure text", "plain text", "text transfer")):
        return None
    range_match = _PAGE_RANGE_RE.search(text)
    if range_match:
        upper = max(_page_count(token) for token in range_match.groups() if token)
    else:
        count_match = _PAGE_COUNT_RE.search(text)
        upper = _page_count(count_match.group(1)) if count_match else 0
    if not 1 <= upper <= 10:
        return None
    return min(3.0, max(1.0, upper * 0.3))


def estimate_simple_effort(title: str, description: str = "") -> float:
    text = f"{title}\n{description}".casefold()
    explicit_micro_effort = _explicit_plain_text_effort(text)
    if explicit_micro_effort is not None:
        return explicit_micro_effort
    if any(term in text for term in ("lead generation", "lead generator", "web search", "market research", "contact list", "data research")):
        return 8.0
    if any(term in text for term in ("proofreading", "editing", "translation", "spreadsheet", "excel")):
        return 8.0
    if any(term in text for term in ("data entry", "copy typing", "transcription")):
        return 12.0
    return 12.0
