from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

AllocationDecision = Literal["stop", "hold", "continue", "accelerate"]


@dataclass(frozen=True)
class MissionEconomics:
    mission_id: str
    sample_size: int
    booked_revenue: float
    booked_gross_profit: float
    expected_gross_profit: float
    conversion_rate: float
    current_budget: float
    strategic_fit: float = 0.5

    def validate(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id is required")
        if self.sample_size < 0:
            raise ValueError("sample_size cannot be negative")
        if self.current_budget < 0:
            raise ValueError("current_budget cannot be negative")
        if not 0 <= self.conversion_rate <= 1:
            raise ValueError("conversion_rate must be between 0 and 1")
        if not 0 <= self.strategic_fit <= 1:
            raise ValueError("strategic_fit must be between 0 and 1")


@dataclass(frozen=True)
class MissionAllocation:
    mission_id: str
    decision: AllocationDecision
    score: float
    previous_budget: float
    allocated_budget: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioReallocation:
    total_budget: float
    allocated_budget: float
    unallocated_budget: float
    allocations: tuple[MissionAllocation, ...]


class EconomicFeedbackReallocator:
    """Reallocate bounded experiment resources using real economic outcomes."""

    def __init__(
        self,
        *,
        minimum_sample_size: int = 5,
        minimum_margin_rate: float = 0.10,
        accelerate_margin_rate: float = 0.25,
        accelerate_conversion_rate: float = 0.20,
        exploration_share: float = 0.15,
        maximum_mission_share: float = 0.50,
    ) -> None:
        if minimum_sample_size <= 0:
            raise ValueError("minimum_sample_size must be positive")
        for value, name in (
            (minimum_margin_rate, "minimum_margin_rate"),
            (accelerate_margin_rate, "accelerate_margin_rate"),
            (accelerate_conversion_rate, "accelerate_conversion_rate"),
            (exploration_share, "exploration_share"),
            (maximum_mission_share, "maximum_mission_share"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.minimum_sample_size = minimum_sample_size
        self.minimum_margin_rate = minimum_margin_rate
        self.accelerate_margin_rate = accelerate_margin_rate
        self.accelerate_conversion_rate = accelerate_conversion_rate
        self.exploration_share = exploration_share
        self.maximum_mission_share = maximum_mission_share

    @staticmethod
    def _margin_rate(item: MissionEconomics) -> float:
        if item.booked_revenue <= 0:
            return 0.0
        return item.booked_gross_profit / item.booked_revenue

    def _classify(self, item: MissionEconomics) -> tuple[AllocationDecision, float, tuple[str, ...]]:
        margin_rate = self._margin_rate(item)
        reasons: list[str] = []
        if item.sample_size >= self.minimum_sample_size and item.expected_gross_profit <= 0:
            return "stop", 0.0, ("sufficient evidence shows non-positive expected gross profit",)
        if item.sample_size >= self.minimum_sample_size and item.booked_revenue > 0 and margin_rate < self.minimum_margin_rate:
            return "hold", 0.15, ("real revenue exists but booked margin is below the minimum gate",)
        score = max(item.expected_gross_profit, 0.0) * (0.5 + 0.5 * item.strategic_fit)
        score *= 0.5 + item.conversion_rate
        if (
            item.sample_size >= self.minimum_sample_size
            and margin_rate >= self.accelerate_margin_rate
            and item.conversion_rate >= self.accelerate_conversion_rate
            and item.booked_gross_profit > 0
        ):
            reasons.append("real margin and conversion satisfy acceleration gates")
            return "accelerate", round(score * 1.5, 6), tuple(reasons)
        if item.sample_size < self.minimum_sample_size:
            reasons.append("insufficient sample; preserve bounded exploration")
            return "continue", round(max(score, item.strategic_fit), 6), tuple(reasons)
        reasons.append("economics remain positive but below acceleration gates")
        return "continue", round(score, 6), tuple(reasons)

    def reallocate(self, missions: Iterable[MissionEconomics], *, total_budget: float) -> PortfolioReallocation:
        if total_budget < 0:
            raise ValueError("total_budget cannot be negative")
        items = tuple(missions)
        if len({item.mission_id for item in items}) != len(items):
            raise ValueError("duplicate mission_id")
        classified: list[tuple[MissionEconomics, AllocationDecision, float, tuple[str, ...]]] = []
        for item in items:
            item.validate()
            decision, score, reasons = self._classify(item)
            classified.append((item, decision, score, reasons))

        exploration_budget = total_budget * self.exploration_share
        exploitation_budget = total_budget - exploration_budget
        active = [row for row in classified if row[1] in {"continue", "accelerate"}]
        total_score = sum(max(row[2], 0.0) for row in active)
        max_per_mission = total_budget * self.maximum_mission_share
        allocations: list[MissionAllocation] = []
        exploratory = [row for row in active if row[0].sample_size < self.minimum_sample_size]
        exploration_each = exploration_budget / len(exploratory) if exploratory else 0.0

        for item, decision, score, reasons in classified:
            amount = 0.0
            if decision in {"continue", "accelerate"}:
                weighted = exploitation_budget * score / total_score if total_score > 0 else 0.0
                amount = weighted + (exploration_each if item.sample_size < self.minimum_sample_size else 0.0)
                amount = min(amount, max_per_mission)
            allocations.append(MissionAllocation(
                mission_id=item.mission_id,
                decision=decision,
                score=score,
                previous_budget=round(item.current_budget, 2),
                allocated_budget=round(amount, 2),
                reasons=reasons,
            ))
        allocations.sort(key=lambda row: (-row.allocated_budget, row.mission_id))
        allocated = round(sum(row.allocated_budget for row in allocations), 2)
        return PortfolioReallocation(
            total_budget=round(total_budget, 2),
            allocated_budget=allocated,
            unallocated_budget=round(max(total_budget - allocated, 0.0), 2),
            allocations=tuple(allocations),
        )

    def write(self, result: PortfolioReallocation, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "economic_reallocation": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
