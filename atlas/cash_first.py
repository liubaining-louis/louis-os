from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal

Decision = Literal["continue", "pivot", "stop", "accelerate"]


@dataclass(frozen=True)
class RevenueAction:
    action_id: str
    strategy_id: str
    stage: Literal["offer", "outreach", "follow_up", "negotiation", "invoice", "payment", "lost"]
    occurred_at: str
    gross_revenue: float = 0.0
    cost: float = 0.0
    qualified_response: bool = False
    rejection_reason: str = ""

    def validate(self) -> None:
        if not self.action_id.strip() or not self.strategy_id.strip():
            raise ValueError("action_id and strategy_id are required")
        if self.gross_revenue < 0 or self.cost < 0:
            raise ValueError("economic amounts cannot be negative")
        if self.stage == "payment" and self.gross_revenue <= 0:
            raise ValueError("a payment requires positive gross revenue")
        datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))


@dataclass(frozen=True)
class CashFirstScorecard:
    strategy_id: str
    decision: Decision
    first_payment_received: bool
    gross_revenue: float
    net_revenue: float
    conversion_rate: float
    qualified_response_rate: float
    follow_ups: int
    days_to_first_payment: float | None
    primary_blocker: str
    next_best_action: str
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CashFirstController:
    """Keep autonomous monetization focused on verified cash, not activity volume."""

    def __init__(self, *, minimum_actions_before_pivot: int = 8, minimum_follow_ups: int = 3) -> None:
        if minimum_actions_before_pivot <= 0 or minimum_follow_ups < 0:
            raise ValueError("thresholds must be non-negative")
        self.minimum_actions_before_pivot = minimum_actions_before_pivot
        self.minimum_follow_ups = minimum_follow_ups

    def evaluate(self, strategy_id: str, actions: Iterable[RevenueAction]) -> CashFirstScorecard:
        items = tuple(actions)
        if not strategy_id.strip():
            raise ValueError("strategy_id is required")
        if not items:
            return CashFirstScorecard(
                strategy_id, "continue", False, 0.0, 0.0, 0.0, 0.0, 0, None,
                "no market action has been executed",
                "publish one concrete paid offer and contact a qualified buyer",
                (),
            )

        seen: set[str] = set()
        for item in items:
            item.validate()
            if item.strategy_id != strategy_id:
                raise ValueError("action belongs to another strategy")
            if item.action_id in seen:
                raise ValueError("duplicate action_id")
            seen.add(item.action_id)

        payments = [item for item in items if item.stage == "payment"]
        outreach = [item for item in items if item.stage in {"outreach", "follow_up"}]
        qualified = [item for item in items if item.qualified_response]
        follow_ups = sum(item.stage == "follow_up" for item in items)
        gross = round(sum(item.gross_revenue for item in payments), 2)
        net = round(gross - sum(item.cost for item in items), 2)
        conversion = round(len(payments) / len(outreach), 6) if outreach else 0.0
        response_rate = round(len(qualified) / len(outreach), 6) if outreach else 0.0
        first_payment_days: float | None = None
        if payments:
            first = min(datetime.fromisoformat(item.occurred_at.replace("Z", "+00:00")) for item in items)
            paid = min(datetime.fromisoformat(item.occurred_at.replace("Z", "+00:00")) for item in payments)
            first_payment_days = round((paid - first).total_seconds() / 86400, 2)

        rejection_reasons = tuple(sorted({item.rejection_reason.strip() for item in items if item.rejection_reason.strip()}))
        if gross > 0 and net > 0:
            decision: Decision = "accelerate"
            blocker = "none: verified profitable payment received"
            next_action = "repeat the winning offer and segment while preserving margin"
        elif qualified and follow_ups < self.minimum_follow_ups:
            decision = "continue"
            blocker = "qualified interest exists but follow-up depth is insufficient"
            next_action = "send the next value-adding follow-up and request a concrete commitment"
        elif len(items) >= self.minimum_actions_before_pivot and not qualified:
            decision = "pivot"
            blocker = "sufficient activity produced no qualified market signal"
            next_action = "change segment, offer or channel and start a bounded replacement experiment"
        elif rejection_reasons:
            decision = "continue"
            blocker = f"rejections identify an offer-market mismatch: {rejection_reasons[0]}"
            next_action = "revise pricing, proof or scope using the recorded rejection reason"
        else:
            decision = "continue"
            blocker = "the pipeline has not reached negotiation or payment"
            next_action = "move the best active prospect to a priced offer with a payment path"

        return CashFirstScorecard(
            strategy_id=strategy_id,
            decision=decision,
            first_payment_received=bool(payments),
            gross_revenue=gross,
            net_revenue=net,
            conversion_rate=conversion,
            qualified_response_rate=response_rate,
            follow_ups=follow_ups,
            days_to_first_payment=first_payment_days,
            primary_blocker=blocker,
            next_best_action=next_action,
            rejection_reasons=rejection_reasons,
        )


def north_star() -> dict[str, object]:
    return {
        "objective": "collect the first legal, verified, non-charcoal euro autonomously",
        "priority_rule": "prefer the safe action with the highest expected probability of verified net cash",
        "required_kpis": [
            "first_payment_received", "gross_revenue", "net_revenue", "conversion_rate",
            "qualified_response_rate", "follow_ups", "days_to_first_payment",
            "revenue_by_strategy", "strategy_abandonment_rate",
        ],
        "cycle_questions": [
            "Was verified cash collected?", "What is the primary blocker?",
            "Which safe action reduces it most?", "Was that action executed and evidenced?",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
