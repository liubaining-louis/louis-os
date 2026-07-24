"""Deterministic readiness checks for externally sourced opportunities.

Commercial attractiveness and execution readiness are intentionally separate.
A large advertised reward must not outrank an opportunity that Louis OS can
actually execute under its current authorization and identity constraints.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class OpportunityReadiness:
    status: str
    execution_score: float
    external_prerequisites: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def executable_now(self) -> bool:
        return self.status == "executable_now"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PREREQUISITE_PATTERNS = (
    (
        "third_party_account_required",
        re.compile(
            r"\b(sign[ -]?up|register|registration|create (?:an? )?account|developer account|platform account)\b",
            re.I,
        ),
    ),
    (
        "maintainer_confirmation_required",
        re.compile(
            r"\b(?:maintainer|owner|organizer).{0,80}\b(?:confirm|approve|select|assign|accept)"
            r"|\bdo not start until\b"
            r"|\bwait (?:for|until).{0,60}\b(?:confirm|approval|assignment)"
            r"|\bmust be confirmed before work begins\b",
            re.I | re.S,
        ),
    ),
    (
        "application_or_claim_required",
        re.compile(
            r"\b(?:apply|application|claim (?:this|the) (?:bounty|task|issue)|would like to claim|request assignment|express interest)\b",
            re.I,
        ),
    ),
    (
        "identity_or_eligibility_check_required",
        re.compile(r"\b(?:KYC|identity verification|proof of eligibility|eligibility verification)\b", re.I),
    ),
    (
        "external_terms_or_contract_required",
        re.compile(
            r"\b(?:accept (?:the )?terms|agree to (?:the )?terms|sign (?:the )?(?:agreement|contract)|contract required)\b",
            re.I,
        ),
    ),
    (
        "payment_or_fee_required",
        re.compile(
            r"\b(?:entry fee|registration fee|pay to enter|payment required|purchase required|deposit required)\b",
            re.I,
        ),
    ),
)


def assess_opportunity_readiness(item: Mapping[str, Any], attractiveness_score: float) -> OpportunityReadiness:
    text = f"{item.get('title', '')}\n{item.get('body', '')}"
    prerequisites: list[str] = []
    evidence: list[str] = []
    for name, pattern in _PREREQUISITE_PATTERNS:
        match = pattern.search(text)
        if match:
            prerequisites.append(name)
            evidence.append(match.group(0).strip()[:160])

    execution_score = max(0.0, float(attractiveness_score) - 25.0 * len(prerequisites))
    return OpportunityReadiness(
        status="gated_external_prerequisite" if prerequisites else "executable_now",
        execution_score=round(execution_score, 1),
        external_prerequisites=tuple(prerequisites),
        evidence=tuple(evidence),
    )


def candidate_is_executable(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("readiness_status") == "executable_now"
        and candidate.get("external_prerequisites_cleared") is True
    )
