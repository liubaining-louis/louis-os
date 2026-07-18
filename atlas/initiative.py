from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .strategic_goals import StrategicGoal


@dataclass(frozen=True)
class Opportunity:
    key: str
    impact: int
    urgency: int
    confidence: float
    effort: int
    risk: int = 0
    requires_approval: bool = False

    def score(self) -> float:
        if not self.key.strip():
            raise ValueError("opportunity key is required")
        if min(self.impact, self.urgency, self.effort, self.risk) < 0:
            raise ValueError("opportunity dimensions must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return round(((self.impact * 2) + self.urgency) * self.confidence - self.effort - (self.risk * 2), 6)


@dataclass(frozen=True)
class ActionBudget:
    max_actions: int = 1
    max_risk: int = 2

    def allows(self, opportunity: Opportunity, actions_used: int = 0) -> bool:
        if self.max_actions < 0 or self.max_risk < 0 or actions_used < 0:
            raise ValueError("budget values must be non-negative")
        return (
            actions_used < self.max_actions
            and opportunity.risk <= self.max_risk
            and not opportunity.requires_approval
        )


def opportunities_from_goals(
    goals: Iterable[StrategicGoal],
    *,
    effort: int = 3,
    risk: int = 1,
) -> list[Opportunity]:
    """Convert active strategic goals into deterministic initiative opportunities.

    Priority controls impact while the remaining metric gap controls urgency. The
    existing action budget remains authoritative for effort, risk and approval.
    """
    if effort < 0 or risk < 0:
        raise ValueError("effort and risk must be non-negative")

    opportunities: list[Opportunity] = []
    for goal in goals:
        goal.validate()
        if goal.status != "active":
            continue
        remaining = 1.0 - goal.progress()
        if remaining <= 0.0:
            continue
        opportunities.append(
            Opportunity(
                key=goal.goal_id,
                impact=max(1, math.ceil(goal.priority / 10)),
                urgency=max(1, math.ceil(remaining * 10)),
                confidence=1.0,
                effort=effort,
                risk=risk,
            )
        )
    return sorted(opportunities, key=lambda item: item.key)


def select_opportunity(
    opportunities: Iterable[Opportunity],
    budget: ActionBudget,
    actions_used: int = 0,
) -> Opportunity | None:
    eligible = [item for item in opportunities if budget.allows(item, actions_used)]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item.score(), item.confidence, item.key))
