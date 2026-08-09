"""Read-only MoltJobs discovery for agent-native, escrowed USDC work.

MoltJobs exposes its OPEN job list publicly. This adapter deliberately stops at
discovery: account claim, terms acceptance, bidding, paid bid credits, work
submission and wallet withdrawal remain separate, explicit authority gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
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
    "password",
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
    "visit an address",
    "visit the address",
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
_ON_CHAIN_PROVIDERS = {"ON_CHAIN_USDC", "ONCHAIN_USDC", "USDC_BASE"}
_FUNDED_PAYMENT_STATES = {"AUTHORIZED", "CAPTURED", "ESCROWED", "FUNDED", "PAID", "PROTECTED", "SUCCEEDED"}


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
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fetch_public_json(
    url: str,
    *,
    timeout_seconds: float,
    maximum_bytes: int,
) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.moltjobs.io" or parsed.path != "/v1/jobs":
        raise ValueError("source only permits the public MoltJobs jobs endpoint")
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Louis-OS-Agent-Market/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: exact HTTPS host checked above
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "api.moltjobs.io" or final.path != "/v1/jobs":
            raise ValueError("MoltJobs redirected outside the permitted endpoint")
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("response exceeds maximum_bytes")
    return payload


def _description(job: Mapping[str, Any]) -> str:
    input_data = job.get("inputData")
    if isinstance(input_data, Mapping):
        primary = str(input_data.get("generalDescription") or "").strip()
        if not primary:
            primary = json.dumps(input_data, ensure_ascii=False, sort_keys=True, default=str)
    else:
        primary = str(input_data or "").strip()
    criteria = job.get("acceptanceCriteria")
    criterion_text: list[str] = []
    if isinstance(criteria, list):
        for item in criteria:
            if isinstance(item, Mapping):
                text = str(item.get("description") or item.get("check") or "").strip()
                if text:
                    criterion_text.append(text)
    combined = primary
    if criterion_text:
        combined = f"{combined}\nAcceptance criteria: {'; '.join(criterion_text)}".strip()
    return combined[:4_000]


def _capability(job: Mapping[str, Any], description: str) -> str:
    template = str(job.get("templateId") or "").casefold()
    text = f"{job.get('title') or ''}\n{description}".casefold()
    if template.startswith("research"):
        return "evidence_research_dossier"
    if any(term in text for term in ("creative brief", "storyboard", "output as json", "structured document")):
        return "structured_document_delivery"
    if any(term in text for term in ("video", "reel", "animation")):
        return "video_content_delivery"
    if any(term in text for term in ("api integration", "webhook", "rest api")):
        return "api_integration_delivery"
    if any(term in text for term in ("frontend bug", "react bug", "css bug")):
        return "frontend_bug_fix"
    if any(term in text for term in ("static website", "landing page", "html website")):
        return "static_website_delivery"
    if any(term in text for term in ("python", "automation script", "data pipeline")):
        return "python_automation_delivery"
    if any(term in text for term in ("research", "analysis", "report", "compare", "find good")):
        return "evidence_research_dossier"
    return "structured_document_delivery"


def _estimated_effort_hours(capability: str) -> float:
    return {
        "evidence_research_dossier": 2.0,
        "structured_document_delivery": 2.0,
        "python_automation_delivery": 2.5,
        "api_integration_delivery": 3.0,
        "frontend_bug_fix": 3.0,
        "static_website_delivery": 3.0,
        "video_content_delivery": 4.0,
    }.get(capability, 3.0)


def _payment_evidence(job: Mapping[str, Any], jobs_url: str, detail_url: str) -> tuple[bool, tuple[str, ...]]:
    provider = str(job.get("paymentProvider") or "").upper()
    state = str(job.get("paymentStatus") or "").upper()
    evidence = [jobs_url, detail_url]
    if provider:
        evidence.append(f"paymentProvider={provider}")
    if state:
        evidence.append(f"paymentStatus={state}")
    for name in ("escrowTxHash", "escrowJobId"):
        value = str(job.get(name) or "").strip()
        if value:
            evidence.append(f"{name}={value}")
    funded = provider in _ON_CHAIN_PROVIDERS or state in _FUNDED_PAYMENT_STATES
    return funded, tuple(evidence)


class MoltJobsAgentJobsSource:
    """Collect fresh public MoltJobs jobs without performing external actions."""

    source_id = "moltjobs_agent_jobs"
    source_category = "agent_native_marketplace"
    jobs_url = "https://api.moltjobs.io/v1/jobs?status=OPEN&limit=100"
    docs_url = "https://moltjobs.io/docs/api"
    terms_url = "https://moltjobs.io/terms"

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
        counts = {"raw": 0, "expired": 0, "payment_unverified": 0, "unsafe": 0, "invalid": 0, "not_open": 0}
        try:
            payload = json.loads(self._fetcher(self.jobs_url).decode("utf-8"))
            raw = payload.get("data") if isinstance(payload, Mapping) else None
            if isinstance(raw, Mapping):
                raw = raw.get("jobs")
            if not isinstance(raw, list):
                raise ValueError("MoltJobs response data must be a list")
            counts["raw"] = len(raw)
            rows: list[InternetOpportunity] = []
            seen: set[str] = set()
            for item in raw:
                if not isinstance(item, Mapping):
                    counts["invalid"] += 1
                    continue
                opportunity, reason = self._parse_job(item)
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
                evidence=(self.jobs_url, self.docs_url, self.terms_url),
                observed_count=0,
            )

        reason = "; ".join(f"{name}={value}" for name, value in counts.items())
        return rows, SourceState(
            source_id=self.source_id,
            category=self.source_category,
            status="ok" if rows else "empty",
            reason=reason,
            evidence=(self.jobs_url, self.docs_url, self.terms_url),
            observed_count=len(rows),
        )

    def _parse_job(self, job: Mapping[str, Any]) -> tuple[InternetOpportunity | None, str]:
        if str(job.get("status") or "").upper() != "OPEN":
            return None, "not_open"
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        deadline = _parse_datetime(job.get("deadlineAt"))
        if deadline is None:
            return None, "invalid"
        if deadline <= now:
            return None, "expired"

        job_id = str(job.get("id") or "").strip()
        title = str(job.get("title") or "").strip()
        amount = _safe_amount(job.get("budgetUsdc"))
        if not job_id or not title or amount <= 0 or amount > self.maximum_budget_usdc:
            return None, "invalid"
        detail_url = f"https://moltjobs.io/open-jobs/{quote(job_id, safe='')}"
        description = _description(job)
        safety_text = f"{title}\n{description}".casefold()
        if any(term in safety_text for term in _PROHIBITED_TERMS + _PHYSICAL_TERMS + _ACCOUNT_CONTROL_TERMS):
            return None, "unsafe"

        reward_verified, payment_evidence = _payment_evidence(job, self.jobs_url, detail_url)
        if not reward_verified:
            return None, "payment_unverified"

        capability = _capability(job, description)
        days_left = max(1, math.ceil((deadline - now).total_seconds() / 86_400))
        provider = str(job.get("paymentProvider") or "").upper()
        payment_status = str(job.get("paymentStatus") or "").upper()
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=detail_url,
            title=title,
            description=description or title,
            reward_amount=amount,
            currency="USDC",
            reward_verified=True,
            payment_evidence=payment_evidence,
            required_capabilities=(capability,),
            observed_at=now.isoformat(),
            deadline=deadline.isoformat(),
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            security_scope_authorized=True,
            physical_presence_required=False,
            accessibility=0.92,
            human_dependency=0.18,
            risk=0.18,
            cost=0.0,
            competition=0.5,
            time_to_cash_days=min(30, days_left + 7),
            evidence=(self.jobs_url, detail_url, self.docs_url, self.terms_url),
            metadata={
                "official_source": True,
                "platform": "MoltJobs",
                "source_kind": "agent_native_public_api",
                "job_id": job_id,
                "template_id": str(job.get("templateId") or ""),
                "deadline_verified": True,
                "days_left": days_left,
                "estimated_effort_hours": _estimated_effort_hours(capability),
                "payout_asset": "USDC",
                "payout_chain": "Base",
                "payment_provider": provider,
                "payment_status": payment_status,
                "submission_mode": "moltjobs_agent_api",
                "bid_endpoint": f"/v1/jobs/{job_id}/bids",
                "submit_endpoint": f"/v1/jobs/{job_id}/submit",
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "operator_gate": "human_owner_claim_and_terms_acceptance",
                "autonomous_bid_enabled": False,
                "paid_bid_credit_purchase_authorized": False,
                "wallet_withdrawal_authorized": False,
                "verified_google_account_required": True,
            },
        ), "accepted"

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_public_json(
            url,
            timeout_seconds=self.timeout_seconds,
            maximum_bytes=self.maximum_bytes,
        )
