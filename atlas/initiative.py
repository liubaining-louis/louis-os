from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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


def select_opportunity(
    opportunities: Iterable[Opportunity],
    budget: ActionBudget,
    actions_used: int = 0,
) -> Opportunity | None:
    eligible = [item for item in opportunities if budget.allows(item, actions_used)]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item.score(), item.confidence, item.key))
