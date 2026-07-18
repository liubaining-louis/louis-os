from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

EvidenceType = Literal["demand", "competition", "pricing", "feasibility", "risk"]
MissionDecision = Literal["ready", "research_more", "reject"]


@dataclass(frozen=True)
class RawMission:
    mission_id: str
    objective: str
    constraints: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.mission_id.strip() or not self.objective.strip():
            raise ValueError("mission_id and objective are required")


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    evidence_type: EvidenceType
    source: str
    claim: str
    reliability: float
    freshness: float
    corroborated: bool

    def validate(self) -> None:
        if not self.evidence_id.strip() or not self.source.strip() or not self.claim.strip():
            raise ValueError("evidence_id, source and claim are required")
        if self.evidence_type not in {"demand", "competition", "pricing", "feasibility", "risk"}:
            raise ValueError("unsupported evidence_type")
        for name in ("reliability", "freshness"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class MissionAssessment:
    mission_id: str
    decision: MissionDecision
    confidence: float
    covered_evidence_types: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    accepted_evidence_ids: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]
    research_questions: tuple[str, ...]
    reasons: tuple[str, ...]


class MissionEvidencePipeline:
    """Gate raw venture missions on diverse, reliable and corroborated evidence."""

    REQUIRED_TYPES: tuple[EvidenceType, ...] = (
        "demand", "competition", "pricing", "feasibility", "risk"
    )

    def __init__(
        self,
        *,
        minimum_reliability: float = 0.55,
        minimum_freshness: float = 0.40,
        minimum_ready_confidence: float = 0.65,
        minimum_types_for_research: int = 2,
    ) -> None:
        for value, name in (
            (minimum_reliability, "minimum_reliability"),
            (minimum_freshness, "minimum_freshness"),
            (minimum_ready_confidence, "minimum_ready_confidence"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not 1 <= minimum_types_for_research <= len(self.REQUIRED_TYPES):
            raise ValueError("minimum_types_for_research is invalid")
        self.minimum_reliability = minimum_reliability
        self.minimum_freshness = minimum_freshness
        self.minimum_ready_confidence = minimum_ready_confidence
        self.minimum_types_for_research = minimum_types_for_research

    def assess(self, mission: RawMission, evidence: Iterable[EvidenceItem]) -> MissionAssessment:
        mission.validate()
        accepted: list[EvidenceItem] = []
        rejected: list[EvidenceItem] = []
        for item in evidence:
            item.validate()
            if item.reliability >= self.minimum_reliability and item.freshness >= self.minimum_freshness:
                accepted.append(item)
            else:
                rejected.append(item)

        covered = tuple(sorted({item.evidence_type for item in accepted}))
        missing = tuple(item for item in self.REQUIRED_TYPES if item not in covered)
        if accepted:
            confidence = sum(
                item.reliability * item.freshness * (1.0 if item.corroborated else 0.75)
                for item in accepted
            ) / len(accepted)
            diversity = len(covered) / len(self.REQUIRED_TYPES)
            confidence = round(0.70 * confidence + 0.30 * diversity, 6)
        else:
            confidence = 0.0

        research_questions = tuple(
            f"Collect reliable, recent evidence for {item}." for item in missing
        )
        reasons: list[str] = []
        if missing:
            reasons.append("required evidence categories are missing")
        if confidence < self.minimum_ready_confidence:
            reasons.append("evidence confidence is below promotion threshold")

        if not missing and confidence >= self.minimum_ready_confidence:
            decision: MissionDecision = "ready"
            reasons = ["evidence coverage and confidence satisfy promotion gate"]
        elif len(covered) >= self.minimum_types_for_research:
            decision = "research_more"
        else:
            decision = "reject"
            reasons.append("mission is too weakly evidenced to enter the venture pipeline")

        return MissionAssessment(
            mission_id=mission.mission_id,
            decision=decision,
            confidence=confidence,
            covered_evidence_types=covered,
            missing_evidence_types=missing,
            accepted_evidence_ids=tuple(sorted(item.evidence_id for item in accepted)),
            rejected_evidence_ids=tuple(sorted(item.evidence_id for item in rejected)),
            research_questions=research_questions,
            reasons=tuple(reasons),
        )

    def write(self, assessment: MissionAssessment, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "assessment": asdict(assessment)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
