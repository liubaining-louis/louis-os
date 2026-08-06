"""Canonical bridge from verified opportunities to submission-ready dossiers.

Only evidence-backed, reversible decisions may produce a dossier. This module never
submits externally and never claims a submission or revenue without a receipt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping

from atlas.decision_intelligence import DecisionCase, DecisionIntelligence


@dataclass(frozen=True)
class GatedDossier:
    dossier_id: str
    opportunity_id: str
    title: str
    canonical_url: str
    decision: str
    decision_confidence: float
    proposal_text: str
    acceptance_criteria: tuple[str, ...]
    estimated_hours: float
    reward_amount: float
    currency: str
    external_submission_verified: bool
    receipt_required: bool
    status: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(opportunity_id: str, canonical_url: str) -> str:
    raw = f"{opportunity_id}|{canonical_url}".encode("utf-8")
    return "dossier-" + hashlib.sha256(raw).hexdigest()[:16]


def _facts(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "listing_open": item.get("listing_open", item.get("fresh_open_verified")),
        "buyer_seeking_worker": item.get("buyer_seeking_worker"),
        "reward_verified": item.get("reward_verified", item.get("payment_verified")),
        "acceptance_criteria": item.get("acceptance_criteria") or item.get("deliverables") or [],
        "remote_eligible": item.get("remote_eligible", True),
        "platform_compliant": item.get("platform_compliant", item.get("legal_policy_pass")),
        "estimated_hours": item.get("estimated_hours", item.get("effort_hours", 0)),
        "reward_amount": item.get("reward_amount", item.get("reward_eur", 0)),
        "minimum_hourly": item.get("minimum_hourly", 8.0),
        "external_action": True,
        "receipt_capture_planned": True,
        "irreversible_commitment": False,
        "source_kind": item.get("source_kind", item.get("source", "internet_opportunity")),
        "platform": item.get("platform"),
        "capability": item.get("capability_id", item.get("capability")),
        "title": item.get("title", "Untitled opportunity"),
    }


def build_dossier(item: Mapping[str, Any], engine: DecisionIntelligence | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    engine = engine or DecisionIntelligence()
    opportunity_id = str(item.get("opportunity_id") or item.get("id") or "").strip()
    canonical_url = str(item.get("canonical_url") or item.get("url") or "").strip()
    title = str(item.get("title") or "Untitled opportunity").strip()
    if not opportunity_id or not canonical_url:
        raise ValueError("opportunity_id and canonical_url are required")

    case = DecisionCase(
        case_id=f"dossier:{opportunity_id}",
        domain="monetization",
        objective="prepare a truthful, payable, externally receipted submission",
        facts=_facts(item),
        proposed_action="prepare a bounded proposal dossier for later authorized submission",
        assumptions=tuple(str(x) for x in item.get("assumptions", []) or []),
        evidence=tuple(str(x) for x in item.get("evidence", []) or []),
    )
    result = engine.evaluate(case)
    decision = result.to_dict()
    if result.decision not in {"proceed_reversibly", "prepare_with_mitigation"}:
        return decision, None

    criteria = tuple(str(x) for x in (_facts(item)["acceptance_criteria"] or []))
    reward = float(_facts(item)["reward_amount"] or 0)
    hours = float(_facts(item)["estimated_hours"] or 0)
    proposal = (
        f"Hello, I can deliver {title} as a bounded, tested task. "
        f"Planned acceptance criteria: {', '.join(criteria) if criteria else 'to be confirmed before work'}. "
        "I will provide the requested artifact, concise validation evidence, and a handoff note. "
        "No material work starts until scope and platform terms are confirmed."
    )
    dossier = GatedDossier(
        dossier_id=_stable_id(opportunity_id, canonical_url),
        opportunity_id=opportunity_id,
        title=title,
        canonical_url=canonical_url,
        decision=result.decision,
        decision_confidence=result.confidence,
        proposal_text=proposal,
        acceptance_criteria=criteria,
        estimated_hours=hours,
        reward_amount=reward,
        currency=str(item.get("currency") or "EUR"),
        external_submission_verified=False,
        receipt_required=True,
        status="prepare_then_gate",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return decision, dossier.to_dict()


def build_pipeline(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    engine = DecisionIntelligence()
    decisions: list[dict[str, Any]] = []
    dossiers: list[dict[str, Any]] = []
    for item in items:
        decision, dossier = build_dossier(item, engine)
        decisions.append(decision)
        if dossier:
            dossiers.append(dossier)
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_count": len(decisions),
        "prepare_then_gate": len(dossiers),
        "execute_now": 0,
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0,
        "decisions": decisions,
        "dossiers": dossiers,
        "submission_contract": {
            "required_before_external_claim": ["fresh page revalidation", "explicit authorization", "platform receipt id"],
            "success_without_receipt_forbidden": True,
        },
    }
