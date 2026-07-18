from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

BudgetDecision = Literal["allocate", "throttle", "defer"]


@dataclass(frozen=True)
class ResourceDemand:
    opportunity_id: str
    priority_score: float
    requested_attention: float
    requested_compute: float
    requested_cost: float
    evidence_confidence: float

    def validate(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        for name in (
            "priority_score",
            "requested_attention",
            "requested_compute",
            "requested_cost",
            "evidence_confidence",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class ResourceAllocation:
    opportunity_id: str
    decision: BudgetDecision
    attention_budget: float
    compute_budget: float
    cost_budget: float
    reasons: tuple[str, ...]


class AutonomousResourceBudgeter:
    """Allocate bounded internal resources across competing opportunities."""

    def __init__(
        self,
        *,
        total_attention_budget: float = 1.0,
        total_compute_budget: float = 1.0,
        total_cost_budget: float = 0.25,
        minimum_evidence_confidence: float = 0.20,
        minimum_allocation: float = 0.02,
    ) -> None:
        for value, name in (
            (total_attention_budget, "total_attention_budget"),
            (total_compute_budget, "total_compute_budget"),
            (total_cost_budget, "total_cost_budget"),
            (minimum_evidence_confidence, "minimum_evidence_confidence"),
            (minimum_allocation, "minimum_allocation"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.total_attention_budget = total_attention_budget
        self.total_compute_budget = total_compute_budget
        self.total_cost_budget = total_cost_budget
        self.minimum_evidence_confidence = minimum_evidence_confidence
        self.minimum_allocation = minimum_allocation

    def allocate(self, demands: Iterable[ResourceDemand]) -> list[ResourceAllocation]:
        items = list(demands)
        for item in items:
            item.validate()
        if not items:
            return []

        eligible = [
            item for item in items
            if item.evidence_confidence >= self.minimum_evidence_confidence and item.priority_score > 0
        ]
        deferred_ids = {item.opportunity_id for item in items if item not in eligible}
        weighted = {
            item.opportunity_id: item.priority_score * item.evidence_confidence
            for item in eligible
        }
        total_weight = sum(weighted.values())
        results: list[ResourceAllocation] = []

        for item in sorted(items, key=lambda value: (-value.priority_score, value.opportunity_id)):
            if item.opportunity_id in deferred_ids or total_weight <= 0:
                results.append(ResourceAllocation(
                    opportunity_id=item.opportunity_id,
                    decision="defer",
                    attention_budget=0.0,
                    compute_budget=0.0,
                    cost_budget=0.0,
                    reasons=("insufficient evidence confidence or priority",),
                ))
                continue

            share = weighted[item.opportunity_id] / total_weight
            attention = min(item.requested_attention, self.total_attention_budget * share)
            compute = min(item.requested_compute, self.total_compute_budget * share)
            cost = min(item.requested_cost, self.total_cost_budget * share)
            decision: BudgetDecision = "allocate"
            reasons: list[str] = ["resource share derived from priority and evidence confidence"]
            if attention + compute + cost < self.minimum_allocation:
                decision = "defer"
                attention = compute = cost = 0.0
                reasons = ["allocation fell below minimum useful threshold"]
            elif (
                attention < item.requested_attention
                or compute < item.requested_compute
                or cost < item.requested_cost
            ):
                decision = "throttle"
                reasons.append("requested resources exceeded bounded portfolio share")

            results.append(ResourceAllocation(
                opportunity_id=item.opportunity_id,
                decision=decision,
                attention_budget=round(attention, 6),
                compute_budget=round(compute, 6),
                cost_budget=round(cost, 6),
                reasons=tuple(reasons),
            ))

        return results

    def write(self, allocations: Iterable[ResourceAllocation], output_path: str | Path) -> str:
        items = list(allocations)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "allocation_count": len(items),
            "allocations": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
