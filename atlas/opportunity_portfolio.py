from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

from atlas.venture_runtime import Opportunity

PortfolioDecision = Literal["invest", "observe", "archive"]


@dataclass(frozen=True)
class PortfolioEntry:
    opportunity_id: str
    score: float
    confidence: float
    expected_return: float
    decision: PortfolioDecision
    resource_share: float
    rationale: dict[str, float]


class OpportunityPortfolioManager:
    """Rank and allocate bounded attention across multiple validated opportunities."""

    def __init__(
        self,
        *,
        maximum_active: int = 3,
        minimum_invest_score: float = 0.40,
        minimum_observe_score: float = 0.20,
    ) -> None:
        if maximum_active <= 0:
            raise ValueError("maximum_active must be positive")
        for value, name in (
            (minimum_invest_score, "minimum_invest_score"),
            (minimum_observe_score, "minimum_observe_score"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if minimum_observe_score > minimum_invest_score:
            raise ValueError("minimum_observe_score cannot exceed minimum_invest_score")
        self.maximum_active = maximum_active
        self.minimum_invest_score = minimum_invest_score
        self.minimum_observe_score = minimum_observe_score

    @staticmethod
    def _score(opportunity: Opportunity) -> tuple[float, float, float, dict[str, float]]:
        opportunity.validate()
        confidence = min(1.0, 0.25 + 0.15 * len(set(opportunity.evidence_references)))
        expected_return = opportunity.expected_value * (1.0 - opportunity.cost) * (1.0 - opportunity.risk)
        rationale = {
            "expected_return": 0.30 * expected_return,
            "autonomy": 0.20 * opportunity.autonomy,
            "learning_value": 0.15 * opportunity.learning_value,
            "speed": 0.10 * opportunity.speed,
            "confidence": 0.15 * confidence,
            "human_dependency_penalty": 0.05 * opportunity.human_dependency,
            "risk_penalty": 0.05 * opportunity.risk,
        }
        score = (
            rationale["expected_return"]
            + rationale["autonomy"]
            + rationale["learning_value"]
            + rationale["speed"]
            + rationale["confidence"]
            - rationale["human_dependency_penalty"]
            - rationale["risk_penalty"]
        )
        return round(score, 6), round(confidence, 6), round(expected_return, 6), rationale

    def allocate(self, opportunities: Iterable[Opportunity]) -> list[PortfolioEntry]:
        ranked: list[tuple[Opportunity, float, float, float, dict[str, float]]] = []
        for opportunity in opportunities:
            score, confidence, expected_return, rationale = self._score(opportunity)
            ranked.append((opportunity, score, confidence, expected_return, rationale))
        ranked.sort(key=lambda item: (-item[1], item[0].opportunity_id))

        investable = [item for item in ranked if item[1] >= self.minimum_invest_score][: self.maximum_active]
        total_invest_score = sum(item[1] for item in investable)
        active_ids = {item[0].opportunity_id for item in investable}

        entries: list[PortfolioEntry] = []
        for opportunity, score, confidence, expected_return, rationale in ranked:
            if opportunity.opportunity_id in active_ids:
                decision: PortfolioDecision = "invest"
                share = score / total_invest_score if total_invest_score else 0.0
            elif score >= self.minimum_observe_score:
                decision = "observe"
                share = 0.0
            else:
                decision = "archive"
                share = 0.0
            entries.append(
                PortfolioEntry(
                    opportunity_id=opportunity.opportunity_id,
                    score=score,
                    confidence=confidence,
                    expected_return=expected_return,
                    decision=decision,
                    resource_share=round(share, 6),
                    rationale=rationale,
                )
            )
        return entries

    def write(self, entries: Iterable[PortfolioEntry], output_path: str | Path) -> str:
        items = list(entries)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "portfolio_count": len(items),
            "active_count": sum(item.decision == "invest" for item in items),
            "entries": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
