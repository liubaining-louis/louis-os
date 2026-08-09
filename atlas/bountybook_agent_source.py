"""Read-only discovery for BountyBook's agent-native, Base-USDC bounties.

The public jobs endpoint can be scanned without a wallet. Authentication,
claiming, submission and any on-chain transaction remain separate execution
steps. The adapter never signs, spends, claims or submits.
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
_UNFUNDED_STATES = {"UNFUNDED", "PENDING", "PENDING_FUNDING", "FAILED", "CANCELLED", "REFUNDED"}


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


def _fetch_public_json(url: str, *, timeout_seconds: float, maximum_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.bountybook.ai" or parsed.path != "/jobs":
        raise ValueError("source only permits the public BountyBook jobs endpoint")
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Louis-OS-Agent-Market/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: exact HTTPS host checked above
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "api.bountybook.ai" or final.path != "/jobs":
            raise ValueError("BountyBook redirected outside the permitted endpoint")
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("response exceeds maximum_bytes")
    return payload


def _spec(job: Mapping[str, Any]) -> Mapping[str, Any]:
    value = job.get("spec")
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"instructions": value}
        return parsed if isinstance(parsed, Mapping) else {"instructions": value}
    return {}


def _description(job: Mapping[str, Any]) -> str:
    spec = _spec(job)
    parts: list[str] = []
    for value in (
        spec.get("instructions"),
        spec.get("description"),
        job.get("description"),
    ):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    criteria = spec.get("acceptanceCriteria", spec.get("acceptance_criteria"))
    if isinstance(criteria, list):
        cleaned = [str(value).strip() for value in criteria if str(value).strip()]
        if cleaned:
            parts.append("Acceptance criteria: " + "; ".join(cleaned))
    return "\n".join(parts)[:4_000]


def _capability(title: str, description: str) -> str:
    text = f"{title}\n{description}".casefold()
    if any(term in text for term in ("csv", "json", "parser", "transform", "convert")):
        return "python_automation_delivery"
    if any(term in text for term in ("api", "webhook", "integration")):
        return "api_integration_delivery"
    if any(term in text for term in ("frontend", "react", "css", "website", "landing page")):
        return "static_website_delivery"
    if any(term in text for term in ("code", "algorithm", "python", "javascript", "typescript", "ci/cd", "test")):
        return "python_automation_delivery"
    if any(term in text for term in ("research", "analysis", "compare", "report")):
        return "evidence_research_dossier"
    return "structured_document_delivery"


def _items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, Mapping):
        raw = payload.get("jobs", payload.get("data"))
        if isinstance(raw, Mapping):
            raw = raw.get("jobs", raw.get("items"))
    else:
        raw = None
    if not isinstance(raw, list):
        raise ValueError("BountyBook response jobs must be a list")
    return [item for item in raw if isinstance(item, Mapping)]


class BountyBookAgentJobsSource:
    """Collect open BountyBook jobs without authenticating or claiming them."""

    source_id = "bountybook_agent_jobs"
    source_category = "agent_native_marketplace"
    jobs_url = "https://api.bountybook.ai/jobs?status=open&limit=100"
    docs_url = "https://www.bountybook.ai/docs"
    terms_url = "https://www.bountybook.ai/terms"

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
            items = _items(payload)
            counts["raw"] = len(items)
            rows: list[InternetOpportunity] = []
            seen: set[str] = set()
            for item in items:
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
        status = str(job.get("status") or "").upper()
        if status != "OPEN":
            return None, "not_open"
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        deadline_value = job.get("deadline", job.get("deadline_at", job.get("expires_at")))
        deadline = _parse_datetime(deadline_value)
        if deadline_value and deadline is None:
            return None, "invalid"
        if deadline is not None and deadline <= now:
            return None, "expired"

        job_id = str(job.get("id") or job.get("job_id") or "").strip()
        title = str(job.get("title") or "").strip()
        amount = _safe_amount(job.get("budget_usdc", job.get("budgetUsdc", job.get("budget"))))
        if not job_id or not title or amount <= 0 or amount > self.maximum_budget_usdc:
            return None, "invalid"
        description = _description(job) or title
        safety_text = f"{title}\n{description}".casefold()
        if any(term in safety_text for term in _PROHIBITED_TERMS + _PHYSICAL_TERMS + _ACCOUNT_CONTROL_TERMS):
            return None, "unsafe"

        payment_state = str(
            job.get("payment_status", job.get("escrow_status", job.get("funding_status", "")))
        ).upper()
        if payment_state in _UNFUNDED_STATES:
            return None, "payment_unverified"
        detail_url = f"https://www.bountybook.ai/job/{quote(job_id, safe='')}"
        payment_evidence = [
            self.jobs_url,
            detail_url,
            f"budget_usdc={amount:g}",
            "official_open_jobs_require_attached_usdc",
        ]
        for name in ("escrow_tx_hash", "escrowTxHash", "tx_hash", "txHash"):
            value = str(job.get(name) or "").strip()
            if value:
                payment_evidence.append(f"{name}={value}")
        if payment_state:
            payment_evidence.append(f"payment_status={payment_state}")

        capability = _capability(title, description)
        days_left = max(1, math.ceil((deadline - now).total_seconds() / 86_400)) if deadline else 7
        return InternetOpportunity(
            source_id=self.source_id,
            source_category=self.source_category,
            source_url=detail_url,
            title=title,
            description=description,
            reward_amount=amount,
            currency="USDC",
            reward_verified=True,
            payment_evidence=tuple(payment_evidence),
            required_capabilities=(capability,),
            observed_at=now.isoformat(),
            deadline=deadline.isoformat() if deadline else "",
            account_required=True,
            terms_required=True,
            identity_or_kyc_required=False,
            security_scope_authorized=True,
            physical_presence_required=False,
            accessibility=0.96,
            human_dependency=0.08,
            risk=0.22,
            cost=0.0,
            competition=0.55,
            time_to_cash_days=min(30, days_left + 3),
            evidence=(self.jobs_url, detail_url, self.docs_url, self.terms_url),
            metadata={
                "official_source": True,
                "platform": "BountyBook",
                "source_kind": "agent_native_public_api",
                "job_id": job_id,
                "deadline_verified": deadline is not None,
                "days_left": days_left,
                "estimated_effort_hours": 2.0,
                "payout_asset": "USDC",
                "payout_chain": "Base",
                "wallet_type": "EVM",
                "submission_mode": "bountybook_agent_api",
                "claim_endpoint": f"/jobs/{job_id}/claim",
                "submit_endpoint": f"/jobs/{job_id}/submit",
                "claim_is_free": True,
                "submission_is_free": True,
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
                "autonomous_claim_enabled": False,
                "financial_transaction_signing_enabled": False,
                "spend_authorized": False,
                "operator_gate": "build_deliverable_before_claim",
            },
        ), "accepted"

    def _default_fetcher(self, url: str) -> bytes:
        return _fetch_public_json(url, timeout_seconds=self.timeout_seconds, maximum_bytes=self.maximum_bytes)
