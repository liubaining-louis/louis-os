"""Deterministic verification gate for internet opportunities.

This module separates factual verification from ranking. It fails closed: an
opportunity cannot be routed to execution or proposal preparation unless the
listing is demonstrably open, payable to the worker, accessible, compliant and
bounded by a clear deliverable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping


TERMINAL_STATUSES = {
    "commercial_offer_not_job",
    "already_assigned",
    "expired_or_closed",
    "geographically_ineligible",
    "platform_policy_blocked",
    "economically_unviable",
}


@dataclass(frozen=True)
class TruthGateResult:
    status: str
    passed: bool
    confidence: float
    blockers: tuple[str, ...]
    checks: Mapping[str, bool]
    evidence_hash: str
    verified_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(opportunity: Mapping[str, Any]) -> str:
    return " ".join(
        str(opportunity.get(name) or "")
        for name in ("title", "description", "deadline")
    ).casefold()


def _bool(metadata: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = metadata.get(name)
    return value if isinstance(value, bool) else default


def verify_opportunity(
    opportunity: Mapping[str, Any],
    *,
    minimum_hourly_eur: float = 8.0,
) -> TruthGateResult:
    metadata = opportunity.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    text = _text(opportunity)

    observed_at = str(opportunity.get("observed_at") or "")
    days_left = int(metadata.get("days_left") or 0)
    explicit_open = _bool(metadata, "status_verified_open") or _bool(metadata, "listing_open")
    listing_open = explicit_open or bool(observed_at and days_left > 0)

    seller_markers = (
        "for sale",
        "rent aws",
        "discount servers",
        "we offer",
        "buy now",
        "selling service",
    )
    payment_markers = (
        "payment for completed work",
        "work completed",
        "already merged",
        "pay contributor",
    )
    policy_markers = (
        "bypass captcha",
        "avoid detection",
        "human detection",
        "mobile proxy",
        "residential proxy",
        "spoof location",
    )
    in_person_markers = (
        "in-person",
        "in person",
        "on site",
        "onsite",
        "retail promoter",
        "store promoter",
    )

    buyer_seeking_worker = _bool(metadata, "buyer_seeking_worker", True) and not any(
        marker in text for marker in seller_markers
    )
    unassigned = not _bool(metadata, "already_assigned") and not any(
        marker in text for marker in payment_markers
    )
    reward_direction_ok = str(metadata.get("reward_direction") or "payer_to_worker") == "payer_to_worker"
    remote_eligible = not bool(opportunity.get("physical_presence_required")) and not any(
        marker in text for marker in in_person_markers
    )
    platform_compliant = not any(marker in text for marker in policy_markers)

    deliverables = opportunity.get("deliverables") or opportunity.get("acceptance_criteria")
    description = str(opportunity.get("description") or "")
    deliverable_clear = bool(deliverables) or len(description.strip()) >= 80

    reward = float(opportunity.get("reward_amount") or 0.0)
    effort = float(metadata.get("estimated_effort_hours") or opportunity.get("effort_hours") or 0.0)
    hourly = reward / effort if reward > 0 and effort > 0 else 0.0
    economics_ok = hourly >= minimum_hourly_eur

    checks = {
        "listing_open": listing_open,
        "buyer_seeking_worker": buyer_seeking_worker,
        "unassigned": unassigned,
        "reward_direction_ok": reward_direction_ok,
        "remote_eligible": remote_eligible,
        "platform_compliant": platform_compliant,
        "deliverable_clear": deliverable_clear,
        "economics_ok": economics_ok,
    }

    blockers = tuple(name for name, passed in checks.items() if not passed)
    status = "verified_payable"
    if not listing_open:
        status = "expired_or_closed"
    elif not buyer_seeking_worker or not reward_direction_ok:
        status = "commercial_offer_not_job"
    elif not unassigned:
        status = "already_assigned"
    elif not remote_eligible:
        status = "geographically_ineligible"
    elif not platform_compliant:
        status = "platform_policy_blocked"
    elif not deliverable_clear:
        status = "deliverable_unclear"
    elif not economics_ok:
        status = "economically_unviable"

    passed = not blockers
    confidence = round(sum(checks.values()) / len(checks), 3)
    evidence_material = "|".join(
        [
            str(opportunity.get("source_url") or ""),
            str(opportunity.get("title") or ""),
            observed_at,
            status,
            ",".join(blockers),
        ]
    )
    evidence_hash = hashlib.sha256(evidence_material.encode("utf-8")).hexdigest()
    return TruthGateResult(
        status=status,
        passed=passed,
        confidence=confidence,
        blockers=blockers,
        checks=checks,
        evidence_hash=evidence_hash,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )
