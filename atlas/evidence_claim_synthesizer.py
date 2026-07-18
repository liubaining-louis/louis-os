from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

ClaimStance = Literal["support", "oppose"]
ClaimDecision = Literal["supported", "contested", "insufficient"]


@dataclass(frozen=True)
class ClaimEvidence:
    claim_key: str
    statement: str
    source_id: str
    source_uri: str
    stance: ClaimStance
    reliability: float
    freshness: float

    def validate(self) -> None:
        if not all(value.strip() for value in (self.claim_key, self.statement, self.source_id, self.source_uri)):
            raise ValueError("claim provenance fields are required")
        if self.stance not in {"support", "oppose"}:
            raise ValueError("unsupported claim stance")
        for name in ("reliability", "freshness"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class SynthesizedClaim:
    claim_key: str
    statement: str
    decision: ClaimDecision
    confidence: float
    support_weight: float
    opposition_weight: float
    supporting_source_ids: tuple[str, ...]
    opposing_source_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class EvidenceClaimSynthesizer:
    """Aggregate evidence into auditable claims while blocking contradictions."""

    def __init__(
        self,
        *,
        minimum_independent_sources: int = 2,
        minimum_confidence: float = 0.60,
        contradiction_margin: float = 0.20,
    ) -> None:
        if minimum_independent_sources <= 0:
            raise ValueError("minimum_independent_sources must be positive")
        for value, name in (
            (minimum_confidence, "minimum_confidence"),
            (contradiction_margin, "contradiction_margin"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.minimum_independent_sources = minimum_independent_sources
        self.minimum_confidence = minimum_confidence
        self.contradiction_margin = contradiction_margin

    def synthesize(self, evidence: Iterable[ClaimEvidence]) -> list[SynthesizedClaim]:
        groups: dict[str, list[ClaimEvidence]] = {}
        for item in evidence:
            item.validate()
            groups.setdefault(item.claim_key, []).append(item)

        results: list[SynthesizedClaim] = []
        for claim_key in sorted(groups):
            items = groups[claim_key]
            statement = sorted(item.statement for item in items)[0]
            support_items = [item for item in items if item.stance == "support"]
            oppose_items = [item for item in items if item.stance == "oppose"]
            support_weight = sum(item.reliability * item.freshness for item in support_items)
            opposition_weight = sum(item.reliability * item.freshness for item in oppose_items)
            total = support_weight + opposition_weight
            confidence = support_weight / total if total else 0.0
            source_count = len({item.source_uri for item in support_items})
            reasons: list[str] = []

            if source_count < self.minimum_independent_sources:
                decision: ClaimDecision = "insufficient"
                reasons.append("too few independent supporting sources")
            elif opposition_weight > 0 and abs(support_weight - opposition_weight) <= self.contradiction_margin * max(total, 1.0):
                decision = "contested"
                reasons.append("supporting and opposing evidence remain materially contradictory")
            elif confidence < self.minimum_confidence:
                decision = "contested"
                reasons.append("opposing evidence prevents promotion")
            else:
                decision = "supported"
                reasons.append("independent weighted evidence satisfies promotion threshold")

            results.append(SynthesizedClaim(
                claim_key=claim_key,
                statement=statement,
                decision=decision,
                confidence=round(confidence, 6),
                support_weight=round(support_weight, 6),
                opposition_weight=round(opposition_weight, 6),
                supporting_source_ids=tuple(sorted(item.source_id for item in support_items)),
                opposing_source_ids=tuple(sorted(item.source_id for item in oppose_items)),
                reasons=tuple(reasons),
            ))
        return results

    def write(self, claims: Iterable[SynthesizedClaim], output_path: str | Path) -> str:
        items = list(claims)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "claim_count": len(items),
            "supported_count": sum(item.decision == "supported" for item in items),
            "contested_count": sum(item.decision == "contested" for item in items),
            "claims": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
