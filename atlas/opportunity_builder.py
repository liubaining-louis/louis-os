from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

ClaimStatus = Literal["supported", "contested", "insufficient"]
BuildDecision = Literal["ready_for_experiment", "revise", "reject"]


@dataclass(frozen=True)
class ValidatedClaim:
    claim_id: str
    category: str
    statement: str
    status: ClaimStatus
    confidence: float
    source_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.claim_id.strip() or not self.category.strip() or not self.statement.strip():
            raise ValueError("claim_id, category and statement are required")
        if self.status not in {"supported", "contested", "insufficient"}:
            raise ValueError("unsupported claim status")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class OpportunityDraft:
    opportunity_id: str
    title: str
    target_customer: str
    problem: str
    offer: str
    revenue_model: str
    expected_value: float
    estimated_cost: float
    risk: float
    autonomy: float
    success_metric: str
    success_threshold: float
    experiment: str
    claim_ids: tuple[str, ...]

    def validate(self) -> None:
        required = (
            self.opportunity_id,
            self.title,
            self.target_customer,
            self.problem,
            self.offer,
            self.revenue_model,
            self.success_metric,
            self.experiment,
        )
        if not all(value.strip() for value in required):
            raise ValueError("all textual opportunity fields are required")
        for name in ("expected_value", "estimated_cost", "risk", "autonomy", "success_threshold"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class OpportunityBuildResult:
    opportunity_id: str
    decision: BuildDecision
    evidence_confidence: float
    supported_categories: tuple[str, ...]
    blocking_claim_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    reasons: tuple[str, ...]
    draft: OpportunityDraft | None


class EvidenceBackedOpportunityBuilder:
    """Promote only commercially complete opportunities grounded in supported claims."""

    REQUIRED_CATEGORIES = ("demand", "competition", "pricing", "feasibility", "risk")

    def __init__(self, *, minimum_claim_confidence: float = 0.60, minimum_ready_confidence: float = 0.68) -> None:
        for value, name in (
            (minimum_claim_confidence, "minimum_claim_confidence"),
            (minimum_ready_confidence, "minimum_ready_confidence"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.minimum_claim_confidence = minimum_claim_confidence
        self.minimum_ready_confidence = minimum_ready_confidence

    def build(self, draft: OpportunityDraft, claims: Iterable[ValidatedClaim]) -> OpportunityBuildResult:
        draft.validate()
        items = list(claims)
        for item in items:
            item.validate()

        referenced = [item for item in items if item.claim_id in set(draft.claim_ids)]
        supported = [
            item for item in referenced
            if item.status == "supported" and item.confidence >= self.minimum_claim_confidence
        ]
        blocking = [item for item in referenced if item not in supported]
        supported_categories = tuple(sorted({item.category for item in supported}))
        missing_categories = tuple(category for category in self.REQUIRED_CATEGORIES if category not in supported_categories)
        evidence_confidence = round(
            sum(item.confidence for item in supported) / len(supported), 6
        ) if supported else 0.0

        assumptions: list[str] = []
        if draft.expected_value <= draft.estimated_cost:
            assumptions.append("expected value does not exceed estimated cost")
        if draft.success_threshold <= 0:
            assumptions.append("success threshold is not meaningful")
        if missing_categories:
            assumptions.append("missing supported categories: " + ", ".join(missing_categories))

        reasons: list[str] = []
        if any(item.status == "contested" for item in referenced):
            decision: BuildDecision = "reject"
            reasons.append("one or more referenced claims are contested")
        elif blocking or missing_categories or evidence_confidence < self.minimum_ready_confidence or assumptions:
            decision = "revise"
            reasons.append("opportunity requires stronger evidence or commercial assumptions")
        else:
            decision = "ready_for_experiment"
            reasons.append("commercial structure and evidence satisfy experiment gate")

        return OpportunityBuildResult(
            opportunity_id=draft.opportunity_id,
            decision=decision,
            evidence_confidence=evidence_confidence,
            supported_categories=supported_categories,
            blocking_claim_ids=tuple(sorted(item.claim_id for item in blocking)),
            assumptions=tuple(assumptions),
            reasons=tuple(reasons),
            draft=draft if decision == "ready_for_experiment" else None,
        )

    def write(self, result: OpportunityBuildResult, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "result": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
