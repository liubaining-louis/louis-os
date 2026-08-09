"""Read-only discovery of open AgentPact buyer needs.

Needs are negotiation leads, not funded work. They are intentionally emitted
with an unverified reward so the market engine cannot start delivery before a
deal is accepted and its USDC escrow is confirmed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], bytes]

_PROHIBITED_TERMS = (
    "fake review",
    "fake testimonial",
    "buy followers",
    "credential theft",
    "steal credentials",
    "malware",
    "ransomware",
    "phishing",
    "bypass access",
    "unauthorized access",
    "sanctions evasion",
    "market manipulation",
    "adult content",
    "gambling",
    "casino",
)
_PHYSICAL_TERMS = (
    "on-site",
    "onsite",
    "in person",
    "field visit",
    "site visit",
    "geotagged photo",
    "physical verification",
)
_ACCOUNT_CONTROL_TERMS = (
    "use your instagram account",
    "use your twitter account",
    "use your x account",
    "post from your account",
    "send direct messages",
    "send dms",
    "mass dm",
    "spam users",
)
_OPEN_STATES = {"OPEN", "ACTIVE", "PUBLISHED"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_amount(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fetch_public_json(url: str, *, timeout_seconds: float, maximum_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.agentpact.xyz" or parsed.path != "/api/needs":
        raise ValueError("source only permits the public AgentPact needs endpoint")
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Louis-OS-Agent-Market/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: exact HTTPS host checked above
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "api.agentpact.xyz" or final.path != "/api/needs":
            raise ValueError("AgentPact redirected outside the permitted endpoint")
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("response exceeds maximum_bytes")
    return payload


def _items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, Mapping):
        raw = payload.get("needs", payload.get("data", payload.get("items")))
        if isinstance(raw, Mapping):
            raw = raw.get("needs", raw.get("items", raw.get("data")))
    else:
        raw = None
    if not isinstance(raw, list):
        raise ValueError("AgentPact response needs must be a list")
    return [item for item in raw if isinstance(item, Mapping)]


def _description(need: Mapping[str, Any]) -> str:
    value = need.get("descriptionMd", need.get("description_md", need.get("description")))
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:4_000]
    return str(value or "").strip()[:4_000]


def _budget(need: Mapping[str, Any]) -> tuple[float, float]:
    low = _safe_amount(
        need.get("budgetMin", need.get("budget_min", need.get("minBudget", need.get("min_price"))))
    )
    high = _safe_amount(
        need.get(
            "budgetMax",
            need.get(
                "budget_max",
                need.get(
                    "maxBudget",
                    need.get("max_price", need.get("budgetUsdc", need.get("budget", need.get("basePrice")))),
                ),
            ),
        )
    )
    if high <= 0:
        high = low
    if low <= 0:
        low = high
    return low, high


def _capability(title: str, description: str, category: str) -> str:
    text = f"{category}\n{title}\n{description}".casefold()
    if any(term in text for term in ("csv", "json", "parser", "transform", "convert", "automation")):
        return "python_automation_delivery"
    if any(term in text for term in ("api", "webhook", "integration")):
        return "api_integration_delivery"
    if any(term in text for term in ("frontend", "react", "css", "website", "landing page")):
        return "static_website_delivery"
    if any(term in text for term in ("research", "analysis", "compare", "report")):
        return "evidence_research_dossier"
    return "structured_document_delivery"


class AgentPactNeedsSource:
    """Collect open AgentPact needs while preserving the escrow-before-work gate."""

    source_id = "agentpact_open_needs"
    source_category = "agent_to_agent_marketplace"
    needs_url = "https://api.agentpact.xyz/api/needs"
    docs_url = "https://agentpact.xyz/api-docs"
    skill_url = "https://agentpact.xyz/skill"

    def __init__(
        self,
        *,
        maximum_budget_usdc: float = 1_000.0,
        maximum_results: int = 50,
        timeout_seconds: float = 20.0,
        maximum_bytes: int = 2_000_000,
        fetcher: Fetcher | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if maximum_budget_usdc <= 0 or maximum_results <= 0 or timeout_seconds <= 0 or maximum_bytes <= 0:
            raise ValueError("source limits must be positive")
        self.maximum_budget_usdc = maximum_budget_usdc
        self.maximum_results = maximum_results
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self._fetcher = fetcher or self._default_fetcher
        self._now = now or _utc_now

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        counts = {"raw": 0, "unsafe": 0, "invalid": 0, "not_open": 0, "unfunded_leads": 0}
        try:
            payload = json.loads(self._fetcher(self.needs_url).decode("utf-8"))
            items = _items(payload)
            counts["raw"] = len(items)
            rows: list[InternetOpportunity] = []
            seen: set[str] = set()
            for item in items:
                opportunity, reason = self._parse_need(item)
                if opportunity is None:
                    counts[reason] = counts.get(reason, 0) + 1
                    continue
                counts["unfunded_leads"] += 1
                if opportunity.source_url in seen:
                    continue
                seen.add(opportunity.source_url)
                rows.append(opportunity)
                if len(rows) >= self.maximum_results:
                    break
        except Exception as exc:
            return [], SourceState(
                source_id=self.source_id,
                category=self.source_category,
                status="failed",
                reason=f"{type(exc).__name__}:{exc}",
                evidence=(self.needs_url, self.docs_url, self.skill_url),
                observed_count=0,
            )

        reason = "; ".join(f"{name}={value}" for name, value in counts.items())
        return rows, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status="partial" if rows else "empty",
            reason=reason,
            evidence=(self.needs_url, self.docs_url, self.skill_url),
            observed_count=len(rows),
        )

    def _parse_need(self, need: Mapping[str, Any]) -> tuple[InternetOpportunity | None, str]:
        status = str(need.get("status") or "OPEN").upper()
        if status not in _OPEN_STATES:
            return None, "not_open"
        need_id = str(need.get("id") or need.get("needId") or need.get("need_id") or "").strip()
        title = str(need.get("title") or "").strip()
        description = _description(need) or title
        budget_low, budget_high = _budget(need)
        if not need_id or not title or budget_high <= 0 or budget_high > self.maximum_budget_usdc:
            return None, "invalid"
        safety_text = f"{title}\n{description}".casefold()
        if any(term in safety_text for term in _PROHIBITED_TERMS + _PHYSICAL_TERMS + _ACCOUNT_CONTROL_TERMS):
            return None, "unsafe"

        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        category = str(need.get("category") or "").strip()
        capability = _capability(title, description, category)
        detail_url = f"https://agentpact.xyz/needs/{quote(need_id, safe='')}"
        sla_days = int(_safe_amount(need.get("slaDays", need.get("sla_days"))) or 1)
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=detail_url,
            title=title,
            description=description,
            reward_amount=budget_high,
            currency="USDC",
            reward_verified=False,
            payment_evidence=(
                self.needs_url,
                detail_url,
                f"budget_range_usdc={budget_low:g}-{budget_high:g}",
                "market_stage=pre_deal_unfunded",
            ),
            required_capabilities=(capability,),
            observed_at=now.isoformat(),
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            security_scope_authorized=True,
            physical_presence_required=False,
            accessibility=0.93,
            human_dependency=0.24,
            risk=0.28,
            cost=0.0,
            competition=0.48,
            time_to_cash_days=min(30, max(2, sla_days + 3)),
            evidence=(self.needs_url, detail_url, self.docs_url, self.skill_url),
            metadata={
                "official_source": True,
                "platform": "AgentPact",
                "source_kind": "agent_to_agent_public_api",
                "need_id": need_id,
                "category": category,
                "budget_min_usdc": budget_low,
                "budget_max_usdc": budget_high,
                "payout_asset": "USDC",
                "payout_chain": "Base",
                "market_stage": "unfunded_need",
                "submission_mode": "agentpact_deal_proposal",
                "proposal_endpoint": "/api/deals/propose",
                "registration_is_free": True,
                "proposal_is_free": True,
                "escrow_required_before_work": True,
                "autonomous_delivery_enabled": False,
                "financial_transaction_signing_enabled": False,
                "spend_authorized": False,
                "operator_gate": "buyer_accepts_and_funds_escrow_before_delivery",
            },
        ), "accepted"

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_public_json(url, timeout_seconds=self.timeout_seconds, maximum_bytes=self.maximum_bytes)
