"""Read active federal prize challenges from the official USA.gov listing.

Challenge.gov was sunset in 2026; USA.gov is now the public index. This adapter only
performs bounded read-only requests to the allowlisted official host and never applies,
accepts rules or represents eligibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]
_LISTING_URL = "https://www.usa.gov/find-active-challenge"
_ALLOWED_HOST = "www.usa.gov"
_MONEY_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
_END_DATE_RE = re.compile(
    r"End date\s*[:\-]?\s*([A-Za-z0-9/, :]+?(?:ET|EST|EDT|PT|PST|PDT|UTC|PM|AM|\d{4}))(?=\s+(?:Challenge type|Prizes|Contact|Apply)|$)",
    re.I,
)


class _ChallengeListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        parsed = urlparse(urljoin(_LISTING_URL, href))
        if parsed.hostname == _ALLOWED_HOST and parsed.path.startswith("/challenges/"):
            canonical = f"https://{_ALLOWED_HOST}{parsed.path.rstrip('/')}"
            if canonical not in self.links:
                self.links.append(canonical)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_h1 = False
        self.title_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self._chunks.append(cleaned)
        if self._in_h1:
            self.title_chunks.append(cleaned)

    @property
    def text(self) -> str:
        return " ".join(self._chunks)

    @property
    def title(self) -> str:
        return " ".join(self.title_chunks).strip()


def _capabilities(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    capabilities: list[str] = ["evidence_research_dossier"]
    if any(term in lowered for term in ("software", "application development", "artificial intelligence", " ai ")):
        capabilities.extend(["technical_proposal", "web_application_prototype"])
    elif any(term in lowered for term in ("business plan", "ideation", "pitch", "design challenge")):
        capabilities.append("technical_proposal")
    if any(term in lowered for term in ("data model", "machine learning", "computer model", "dataset")):
        capabilities.append("python_data_analysis")
    if any(term in lowered for term in ("hardware", "robotics", "prototype demonstration", "physical prototype")):
        capabilities.append("physical_hardware_prototype")
    return tuple(dict.fromkeys(capabilities))


def _physical_presence(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in ("in-person only", "must attend in person", "on-site only"))


def _accessibility(text: str) -> float:
    lowered = text.casefold()
    if any(term in lowered for term in ("around the world", "worldwide", "allied foreign countries", "international")):
        return 0.85
    if any(term in lowered for term in ("u.s. citizens only", "united states citizens only", "eligible u.s. businesses")):
        return 0.10
    if "businesses" in lowered or "organizations" in lowered:
        return 0.45
    return 0.55


class USAGovChallengeSource:
    source_id = "usagov_challenges"
    source_category = "challenge_prize"

    def __init__(
        self,
        *,
        listing_url: str = _LISTING_URL,
        maximum_challenges: int = 20,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 2_000_000,
        fetcher: Fetcher | None = None,
    ) -> None:
        parsed = urlparse(listing_url)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST:
            raise ValueError("USA.gov listing URL must use the allowlisted official host")
        if maximum_challenges <= 0 or timeout_seconds <= 0 or maximum_bytes <= 0:
            raise ValueError("source limits must be positive")
        self.listing_url = listing_url
        self.maximum_challenges = maximum_challenges
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        try:
            listing = self._fetcher(self.listing_url)
            if len(listing) > self.maximum_bytes:
                raise ValueError("USA.gov listing exceeds maximum_bytes")
            parser = _ChallengeListingParser()
            parser.feed(listing.decode("utf-8"))
        except Exception as exc:
            state = SourceState(
                source_id=self.source_id,
                category=self.source_category,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
                evidence=(self.listing_url,),
                observed_count=0,
            )
            return [], state

        opportunities: list[InternetOpportunity] = []
        errors: list[str] = []
        for url in parser.links[: self.maximum_challenges]:
            try:
                raw = self._fetcher(url)
                if len(raw) > self.maximum_bytes:
                    raise ValueError("challenge detail exceeds maximum_bytes")
                opportunity = self._parse_detail(url, raw.decode("utf-8"))
                if opportunity is not None:
                    opportunities.append(opportunity)
            except Exception as exc:
                errors.append(f"{url}:{type(exc).__name__}:{exc}")

        status = "ok" if opportunities else "empty"
        if errors and opportunities:
            status = "partial"
        elif errors and not opportunities:
            status = "failed"
        state = SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status=status,
            reason="; ".join(errors[:5]),
            evidence=(self.listing_url,),
            observed_count=len(opportunities),
        )
        return opportunities, state

    def _parse_detail(self, url: str, html: str) -> InternetOpportunity | None:
        parser = _TextParser()
        parser.feed(html)
        text = parser.text
        title = parser.title
        if not title or "Prizes" not in text:
            return None
        amounts = [float(raw.replace(",", "")) for raw in _MONEY_RE.findall(text)]
        reward = max(amounts) if amounts else 0.0
        reward_verified = reward > 0
        deadline_match = _END_DATE_RE.search(text)
        deadline = deadline_match.group(1).strip() if deadline_match else ""
        evidence_excerpt = re.sub(r"\s+", " ", text)
        prize_index = evidence_excerpt.casefold().find("prizes")
        if prize_index >= 0:
            evidence_excerpt = evidence_excerpt[prize_index : prize_index + 420]
        else:
            evidence_excerpt = evidence_excerpt[:420]

        capabilities = _capabilities(text)
        accessibility = _accessibility(text)
        physical = _physical_presence(text)
        legal_entity = any(term in text.casefold() for term in ("small businesses", "large businesses", "eligible businesses"))
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=url,
            title=title,
            description=text[:4000],
            reward_amount=reward,
            currency="USD",
            reward_verified=reward_verified,
            payment_evidence=(url, evidence_excerpt) if reward_verified else (),
            required_capabilities=capabilities,
            observed_at=datetime.now(timezone.utc).isoformat(),
            deadline=deadline,
            account_required=True,
            terms_required=True,
            legal_entity_required=legal_entity,
            identity_or_kyc_required=True,
            security_scope_authorized=True,
            physical_presence_required=physical,
            accessibility=accessibility,
            human_dependency=0.55,
            risk=0.25,
            cost=0.25 if "hardware" not in text.casefold() else 0.70,
            competition=0.80,
            time_to_cash_days=120,
            evidence=(self.listing_url, url),
            metadata={"official_source": True, "source_kind": "federal_challenge_index"},
        )

    def _default_fetcher(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST:
            raise ValueError("request host is not allowlisted")
        request = Request(
            url,
            headers={"Accept": "text/html", "User-Agent": "Louis-OS-Universal-Market/1.0"},
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310: host is allowlisted
            body = response.read(self.maximum_bytes + 1)
        if len(body) > self.maximum_bytes:
            raise ValueError("USA.gov response exceeds maximum_bytes")
        return body
