from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    title: str
    problem: str
    target_customer: str
    proposed_offer: str
    evidence_references: list[str]
    expected_value: float
    autonomy: float
    learning_value: float
    speed: float
    human_dependency: float
    cost: float
    risk: float

    def validate(self) -> None:
        required = {
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "problem": self.problem,
            "target_customer": self.target_customer,
            "proposed_offer": self.proposed_offer,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing opportunity fields: {', '.join(missing)}")
        if not self.evidence_references:
            raise ValueError("at least one evidence reference is required")
        for name in (
            "expected_value",
            "autonomy",
            "learning_value",
            "speed",
            "human_dependency",
            "cost",
            "risk",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class DecisionWeights:
    expected_value: float = 0.24
    autonomy: float = 0.22
    learning_value: float = 0.16
    speed: float = 0.12
    human_dependency: float = 0.10
    cost: float = 0.08
    risk: float = 0.08

    def validate(self) -> None:
        values = asdict(self)
        if any(value < 0 for value in values.values()):
            raise ValueError("decision weights must be non-negative")
        if abs(sum(values.values()) - 1.0) > 1e-9:
            raise ValueError("decision weights must sum to 1")


@dataclass(frozen=True)
class RankedOpportunity:
    opportunity: Opportunity
    score: float
    rationale: dict[str, float]


class VentureDecisionEngine:
    def __init__(self, weights: DecisionWeights | None = None) -> None:
        self.weights = weights or DecisionWeights()
        self.weights.validate()

    def score(self, opportunity: Opportunity) -> RankedOpportunity:
        opportunity.validate()
        w = self.weights
        rationale = {
            "expected_value": opportunity.expected_value * w.expected_value,
            "autonomy": opportunity.autonomy * w.autonomy,
            "learning_value": opportunity.learning_value * w.learning_value,
            "speed": opportunity.speed * w.speed,
            "human_dependency_penalty": opportunity.human_dependency * w.human_dependency,
            "cost_penalty": opportunity.cost * w.cost,
            "risk_penalty": opportunity.risk * w.risk,
        }
        score = (
            rationale["expected_value"]
            + rationale["autonomy"]
            + rationale["learning_value"]
            + rationale["speed"]
            - rationale["human_dependency_penalty"]
            - rationale["cost_penalty"]
            - rationale["risk_penalty"]
        )
        return RankedOpportunity(opportunity=opportunity, score=round(score, 6), rationale=rationale)

    def rank(self, opportunities: Iterable[Opportunity]) -> list[RankedOpportunity]:
        ranked = [self.score(opportunity) for opportunity in opportunities]
        return sorted(ranked, key=lambda item: (-item.score, item.opportunity.opportunity_id))


@dataclass(frozen=True)
class VentureEvent:
    event_type: str
    venture_id: str
    payload: dict[str, Any]
    evidence_references: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> None:
        if not self.event_type.strip() or not self.venture_id.strip():
            raise ValueError("event_type and venture_id are required")
        if self.event_type in {"opportunity_observed", "hypothesis_selected", "result_recorded"} and not self.evidence_references:
            raise ValueError(f"{self.event_type} requires evidence references")


class JsonlVentureMemory:
    """Append-only entrepreneurial memory that is deterministic and auditable."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: VentureEvent) -> None:
        event.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")

    def read_all(self) -> list[VentureEvent]:
        if not self.path.exists():
            return []
        events: list[VentureEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    event = VentureEvent(**data)
                    event.validate()
                    events.append(event)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid venture memory at line {line_number}: {exc}") from exc
        return events


@dataclass(frozen=True)
class VentureEdge:
    source: str
    relation: str
    target: str
    evidence_references: list[str] = field(default_factory=list)


class VentureGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[VentureEdge] = []

    def add_node(self, node_id: str, node_type: str, **attributes: Any) -> None:
        if not node_id.strip() or not node_type.strip():
            raise ValueError("node_id and node_type are required")
        existing = self._nodes.get(node_id)
        value = {"type": node_type, **attributes}
        if existing is not None and existing != value:
            raise ValueError(f"conflicting node definition: {node_id}")
        self._nodes[node_id] = value

    def add_edge(self, edge: VentureEdge) -> None:
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise ValueError("edge endpoints must exist")
        if edge in self._edges:
            return
        self._edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(sorted(self._nodes.items())),
            "edges": [asdict(edge) for edge in sorted(self._edges, key=lambda e: (e.source, e.relation, e.target))],
        }


@dataclass(frozen=True)
class CeoDecision:
    selected_opportunity_id: str
    score: float
    next_action: str
    approval_required: bool
    rejection_reasons: dict[str, str]


class CeoAgent:
    """Deterministic CEO policy: select one evidence-backed, high-autonomy opportunity."""

    def __init__(self, engine: VentureDecisionEngine | None = None, minimum_score: float = 0.10) -> None:
        self.engine = engine or VentureDecisionEngine()
        self.minimum_score = minimum_score

    def decide(self, opportunities: Iterable[Opportunity]) -> CeoDecision:
        ranked = self.engine.rank(opportunities)
        if not ranked:
            raise ValueError("at least one opportunity is required")

        rejection_reasons: dict[str, str] = {}
        eligible: list[RankedOpportunity] = []
        for item in ranked:
            opportunity = item.opportunity
            if opportunity.human_dependency > 0.35:
                rejection_reasons[opportunity.opportunity_id] = "human dependency exceeds 35%"
            elif opportunity.risk > 0.70:
                rejection_reasons[opportunity.opportunity_id] = "risk exceeds 70%"
            elif item.score < self.minimum_score:
                rejection_reasons[opportunity.opportunity_id] = "decision score below threshold"
            else:
                eligible.append(item)

        if not eligible:
            raise ValueError("no opportunity passed CEO policy gates")

        winner = eligible[0]
        action = (
            f"Create a bounded dry-run asset for '{winner.opportunity.proposed_offer}' "
            "and record one measurable validation experiment."
        )
        return CeoDecision(
            selected_opportunity_id=winner.opportunity.opportunity_id,
            score=winner.score,
            next_action=action,
            approval_required=False,
            rejection_reasons=rejection_reasons,
        )


def build_dry_run_artifact(
    venture_id: str,
    decision: CeoDecision,
    ranked: list[RankedOpportunity],
    output_path: str | Path,
) -> dict[str, Any]:
    if not venture_id.strip():
        raise ValueError("venture_id is required")
    artifact = {
        "schema_version": "1.0",
        "venture_id": venture_id,
        "mode": "dry_run",
        "selected_opportunity_id": decision.selected_opportunity_id,
        "decision_score": decision.score,
        "next_action": decision.next_action,
        "approval_required": decision.approval_required,
        "ranking": [
            {
                "opportunity_id": item.opportunity.opportunity_id,
                "score": item.score,
                "evidence_references": item.opportunity.evidence_references,
                "rationale": item.rationale,
            }
            for item in ranked
        ],
        "rejection_reasons": decision.rejection_reasons,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return artifact
