"""Convert external success evidence into bounded, testable playbooks."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


_EVIDENCE_WEIGHT = {
    "primary_research": 1.00,
    "audited_report": 0.95,
    "documented_case_study": 0.82,
    "independent_practitioner_pattern": 0.70,
    "operator_account_with_receipts": 0.62,
    "opinion_or_promotion": 0.25,
}


@dataclass(frozen=True)
class SuccessEvidence:
    source_url: str
    source_domain: str
    published_at: str | None
    evidence_type: str
    actor: str
    context: str
    mechanism: str
    outcome: str
    independent_group: str
    has_concrete_metrics: bool = False
    has_failure_conditions: bool = False
    promotional_conflict: bool = False


@dataclass(frozen=True)
class PlaybookHypothesis:
    hypothesis_id: str
    mechanism: str
    confidence: float
    evidence_count: int
    independent_groups: int
    survivorship_risk: str
    transfer_status: str
    experiment: Mapping[str, Any]
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_score(item: SuccessEvidence) -> float:
    score = _EVIDENCE_WEIGHT.get(item.evidence_type, 0.20)
    if item.has_concrete_metrics:
        score += 0.08
    if item.has_failure_conditions:
        score += 0.07
    if item.promotional_conflict:
        score -= 0.20
    return round(max(0.0, min(1.0, score)), 4)


def build_playbook(mechanism: str, evidence: Iterable[SuccessEvidence]) -> PlaybookHypothesis:
    rows = [item for item in evidence if item.mechanism.strip().lower() == mechanism.strip().lower()]
    groups = {item.independent_group for item in rows if item.independent_group}
    scores = [evidence_score(item) for item in rows]
    base = sum(scores) / len(scores) if scores else 0.0
    diversity_bonus = min(0.15, max(0, len(groups) - 1) * 0.05)
    confidence = round(min(0.95, base * 0.75 + diversity_bonus), 4)
    if len(rows) < 2 or len(groups) < 2:
        survivorship = "high"
        transfer = "hypothesis_only"
    elif confidence >= 0.70:
        survivorship = "medium"
        transfer = "bounded_experiment_ready"
    else:
        survivorship = "medium_high"
        transfer = "needs_more_corroboration"
    slug = "".join(ch if ch.isalnum() else "-" for ch in mechanism.lower()).strip("-")[:60]
    return PlaybookHypothesis(
        hypothesis_id=f"best-practice-{slug}",
        mechanism=mechanism,
        confidence=confidence,
        evidence_count=len(rows),
        independent_groups=len(groups),
        survivorship_risk=survivorship,
        transfer_status=transfer,
        experiment={
            "scope": "small reversible commercial experiment",
            "success_metric": "verified improvement in response, conversion, delivery acceptance or payment rate",
            "stop_rule": "stop on legal, platform, quality or negative-unit-economics evidence",
            "max_unverified_claims": 0,
        },
        sources=tuple(dict.fromkeys(item.source_url for item in rows)),
    )


def learning_manifest(playbooks: Iterable[PlaybookHypothesis]) -> dict[str, Any]:
    rows = [item.to_dict() for item in playbooks]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "learn transferable mechanisms from documented success without copying anecdotes blindly",
        "playbooks": rows,
        "counts": {
            "playbooks": len(rows),
            "experiment_ready": sum(item["transfer_status"] == "bounded_experiment_ready" for item in rows),
        },
        "truth": {
            "external_success_is_not_louis_os_revenue": True,
            "experiments_require_receipts": True,
            "internet_access_broad_but_methods_must_remain_legal_and_attributed": True,
        },
    }
