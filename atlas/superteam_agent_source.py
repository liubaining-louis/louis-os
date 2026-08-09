"""Authenticated discovery of Superteam Earn listings open to AI agents."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .universal_market import InternetOpportunity, SourceState


Fetcher = Callable[[str], Mapping[str, Any]]

_PROHIBITED_TERMS = (
    "fake review",
    "fake testimonial",
    "buy followers",
    "credential theft",
    "malware",
    "ransomware",
    "phishing",
    "unauthorized access",
    "sanctions evasion",
    "market manipulation",
    "adult content",
    "gambling",
    "casino",
)
_PHYSICAL_TERMS = ("on-site", "onsite", "in person", "field visit", "site visit", "physical verification")
_ACCOUNT_CONTROL_TERMS = (
    "use your instagram account",
    "use your twitter account",
    "use your x account",
    "post from your account",
    "send direct messages",
    "mass dm",
    "spam users",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_amount(value: Any) -> float:
    if isinstance(value, Mapping):
        value = value.get("amount", value.get("value"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw: Any = None
    for key in ("listings", "data", "items"):
        if key in payload:
            raw = payload.get(key)
            break
    if isinstance(raw, Mapping):
        raw = raw.get("listings", raw.get("items", raw.get("data")))
    if not isinstance(raw, list):
        raise ValueError("Superteam response listings must be a list")
    return [item for item in raw if isinstance(item, Mapping)]


def _description(item: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for name in ("description", "shortDescription", "requirements", "eligibility"):
        value = item.get(name)
        if isinstance(value, (list, Mapping)):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        else:
            text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)[:4_000]


def _capability(title: str, description: str) -> str:
    text = f"{title}\n{description}".casefold()
    if any(term in text for term in ("api", "webhook", "integration")):
        return "api_integration_delivery"
    if any(term in text for term in ("python", "automation", "csv", "json", "code", "developer")):
        return "python_automation_delivery"
    if any(term in text for term in ("frontend", "website", "landing page", "react", "design")):
        return "static_website_delivery"
    if any(term in text for term in ("research", "analysis", "report", "compare")):
        return "evidence_research_dossier"
    return "structured_document_delivery"


class SuperteamAgentListingsSource:
    """Collect only fresh AGENT_ALLOWED or AGENT_ONLY Superteam listings."""

    source_id = "superteam_agent_earn"
    source_category = "agent_bounty_marketplace"
    api_url = "https://superteam.fun/api/agents/listings/live?take=100"
    docs_url = "https://superteam.fun/earn/agents"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        maximum_budget: float = 10_000.0,
        maximum_results: int = 50,
        fetcher: Fetcher | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if maximum_budget <= 0 or maximum_results <= 0:
            raise ValueError("source limits must be positive")
        self.api_key = api_key if api_key is not None else os.getenv("SUPERTEAM_API_KEY", "")
        self.maximum_budget = maximum_budget
        self.maximum_results = maximum_results
        self._fetcher = fetcher or self._default_fetcher
        self._now = now or _utc_now

    def collect(self) -> tuple[list[InternetOpportunity], SourceState]:
        if not self.api_key.strip():
            return [], SourceState(
                source_id=self.source_id,
                category=self.source_category,
                status="credential_gated",
                reason="superteam_api_key_missing",
                evidence=(self.api_url, self.docs_url),
                observed_count=0,
            )
        counts = {"raw": 0, "expired": 0, "unsafe": 0, "invalid": 0, "not_open": 0, "agent_ineligible": 0}
        try:
            payload = self._fetcher(self.api_key)
            items = _items(payload)
            counts["raw"] = len(items)
            rows: list[InternetOpportunity] = []
            seen: set[str] = set()
            for item in items:
                opportunity, reason = self._parse_listing(item)
                if opportunity is None:
                    counts[reason] = counts.get(reason, 0) + 1
                    continue
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
                evidence=(self.api_url, self.docs_url),
                observed_count=0,
            )

        reason = "; ".join(f"{name}={value}" for name, value in counts.items())
        return rows, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status="ok" if rows else "empty",
            reason=reason,
            evidence=(self.api_url, self.docs_url),
            observed_count=len(rows),
        )

    def _parse_listing(self, item: Mapping[str, Any]) -> tuple[InternetOpportunity | None, str]:
        access = str(item.get("agentAccess") or item.get("agent_access") or "").upper()
        if access not in {"AGENT_ALLOWED", "AGENT_ONLY"}:
            return None, "agent_ineligible"
        if bool(item.get("isWinnersAnnounced")):
            return None, "not_open"
        status = str(item.get("status") or "OPEN").upper()
        if status != "OPEN":
            return None, "not_open"
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        deadline_value = item.get("deadline")
        deadline = _parse_datetime(deadline_value)
        if deadline_value and deadline is None:
            return None, "invalid"
        if deadline is not None and deadline <= now:
            return None, "expired"

        listing_id = str(item.get("id") or item.get("listingId") or "").strip()
        slug = str(item.get("slug") or listing_id).strip()
        title = str(item.get("title") or "").strip()
        amount = _safe_amount(item.get("rewardAmount", item.get("reward", item.get("amount"))))
        if not listing_id or not slug or not title or amount <= 0 or amount > self.maximum_budget:
            return None, "invalid"
        description = _description(item) or title
        safety_text = f"{title}\n{description}".casefold()
        if any(term in safety_text for term in _PROHIBITED_TERMS + _PHYSICAL_TERMS + _ACCOUNT_CONTROL_TERMS):
            return None, "unsafe"

        currency = str(item.get("rewardCurrency") or item.get("currency") or "USDC").upper()
        detail_url = f"https://superteam.fun/earn/listing/{quote(slug, safe='-')}"
        capability = _capability(title, description)
        days_left = max(1, math.ceil((deadline - now).total_seconds() / 86_400)) if deadline else 7
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=detail_url,
            title=title,
            description=description,
            reward_amount=amount,
            currency=currency,
            reward_verified=True,
            payment_evidence=(self.api_url, detail_url, f"reward={amount:g} {currency}"),
            required_capabilities=(capability,),
            observed_at=now.isoformat(),
            deadline=deadline.isoformat() if deadline else "",
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            security_scope_authorized=True,
            physical_presence_required=False,
            accessibility=0.95,
            human_dependency=0.12,
            risk=0.18,
            cost=0.0,
            competition=0.62,
            time_to_cash_days=min(30, days_left + 7),
            evidence=(self.api_url, detail_url, self.docs_url),
            metadata={
                "official_source": True,
                "platform": "Superteam Earn",
                "source_kind": "authenticated_agent_api",
                "listing_id": listing_id,
                "slug": slug,
                "agent_access": access,
                "deadline_verified": deadline is not None,
                "days_left": days_left,
                "estimated_effort_hours": 3.0,
                "payout_asset": currency,
                "submission_mode": "superteam_agent_api",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "operator_gate": "human_claims_payout_after_acceptance",
                "autonomous_submission_enabled": True,
                "spend_authorized": False,
            },
        ), "accepted"

    @staticmethod
    def _default_fetcher(api_key: str) -> Mapping[str, Any]:
        from .superteam_agent import live_listings

        return live_listings(api_key, take=100)
