from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

OutcomeStage = Literal["lead", "quote", "order", "lost"]
EconomicDecision = Literal["continue", "revise", "stop", "accelerate"]


@dataclass(frozen=True)
class EconomicOutcome:
    outcome_id: str
    experiment_id: str
    prospect_id: str
    stage: OutcomeStage
    revenue: float = 0.0
    variable_cost: float = 0.0
    fixed_cost_allocated: float = 0.0
    conversion_probability: float = 0.0
    currency: str = "EUR"

    def validate(self) -> None:
        if not all(value.strip() for value in (self.outcome_id, self.experiment_id, self.prospect_id, self.currency)):
            raise ValueError("outcome, experiment, prospect and currency are required")
        if self.stage not in {"lead", "quote", "order", "lost"}:
            raise ValueError("unsupported outcome stage")
        if min(self.revenue, self.variable_cost, self.fixed_cost_allocated) < 0:
            raise ValueError("economic amounts cannot be negative")
        if not 0 <= self.conversion_probability <= 1:
            raise ValueError("conversion_probability must be between 0 and 1")
        if self.stage == "order" and self.revenue <= 0:
            raise ValueError("an order requires positive revenue")
        if self.stage == "lost" and self.conversion_probability != 0:
            raise ValueError("a lost outcome must have zero conversion probability")


@dataclass(frozen=True)
class EconomicSummary:
    experiment_id: str
    decision: EconomicDecision
    leads: int
    quotes: int
    orders: int
    losses: int
    booked_revenue: float
    expected_revenue: float
    booked_gross_profit: float
    expected_gross_profit: float
    booked_margin_rate: float
    expected_margin_rate: float
    quote_to_order_rate: float
    reasons: tuple[str, ...]
    next_actions: tuple[str, ...]


class EconomicOutcomeLedger:
    """Aggregate auditable market outcomes into deterministic economic decisions."""

    def __init__(
        self,
        *,
        minimum_observations: int = 5,
        minimum_margin_rate: float = 0.15,
        accelerate_margin_rate: float = 0.25,
        minimum_quote_to_order_rate: float = 0.10,
    ) -> None:
        if minimum_observations <= 0:
            raise ValueError("minimum_observations must be positive")
        for value, name in (
            (minimum_margin_rate, "minimum_margin_rate"),
            (accelerate_margin_rate, "accelerate_margin_rate"),
            (minimum_quote_to_order_rate, "minimum_quote_to_order_rate"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if accelerate_margin_rate < minimum_margin_rate:
            raise ValueError("accelerate margin cannot be below minimum margin")
        self.minimum_observations = minimum_observations
        self.minimum_margin_rate = minimum_margin_rate
        self.accelerate_margin_rate = accelerate_margin_rate
        self.minimum_quote_to_order_rate = minimum_quote_to_order_rate

    def summarize(self, experiment_id: str, outcomes: Iterable[EconomicOutcome]) -> EconomicSummary:
        if not experiment_id.strip():
            raise ValueError("experiment_id is required")
        items = tuple(outcomes)
        seen_ids: set[str] = set()
        currencies: set[str] = set()
        for item in items:
            item.validate()
            if item.experiment_id != experiment_id:
                raise ValueError("outcome belongs to another experiment")
            if item.outcome_id in seen_ids:
                raise ValueError("duplicate outcome_id")
            seen_ids.add(item.outcome_id)
            currencies.add(item.currency)
        if len(currencies) > 1:
            raise ValueError("mixed currencies require prior normalization")

        leads = sum(item.stage == "lead" for item in items)
        quotes = sum(item.stage == "quote" for item in items)
        orders = sum(item.stage == "order" for item in items)
        losses = sum(item.stage == "lost" for item in items)

        booked_revenue = round(sum(item.revenue for item in items if item.stage == "order"), 2)
        expected_revenue = round(sum(item.revenue * item.conversion_probability for item in items), 2)
        booked_cost = sum(
            item.variable_cost + item.fixed_cost_allocated for item in items if item.stage == "order"
        )
        expected_cost = sum(
            (item.variable_cost + item.fixed_cost_allocated) * item.conversion_probability for item in items
        )
        booked_profit = round(booked_revenue - booked_cost, 2)
        expected_profit = round(expected_revenue - expected_cost, 2)
        booked_margin = round(booked_profit / booked_revenue, 6) if booked_revenue else 0.0
        expected_margin = round(expected_profit / expected_revenue, 6) if expected_revenue else 0.0
        quote_to_order = round(orders / quotes, 6) if quotes else 0.0

        reasons: list[str] = []
        next_actions: list[str] = []
        if len(items) < self.minimum_observations:
            decision: EconomicDecision = "continue"
            reasons.append("economic sample is below the minimum observation threshold")
            next_actions.append("collect additional quoted, won or lost outcomes")
        elif booked_revenue > 0 and booked_margin >= self.accelerate_margin_rate and quote_to_order >= self.minimum_quote_to_order_rate:
            decision = "accelerate"
            reasons.append("booked margin and quote conversion satisfy acceleration gates")
            next_actions.append("increase the bounded experiment budget")
        elif expected_margin < self.minimum_margin_rate or (quotes and quote_to_order < self.minimum_quote_to_order_rate):
            decision = "stop" if booked_revenue == 0 and expected_margin <= 0 else "revise"
            reasons.append("economic quality is below the required margin or conversion gate")
            next_actions.append("revise pricing, costs, segment or value proposition")
        else:
            decision = "continue"
            reasons.append("economics are viable but do not yet satisfy acceleration gates")
            next_actions.append("continue the experiment within the current budget")

        return EconomicSummary(
            experiment_id=experiment_id,
            decision=decision,
            leads=leads,
            quotes=quotes,
            orders=orders,
            losses=losses,
            booked_revenue=booked_revenue,
            expected_revenue=expected_revenue,
            booked_gross_profit=booked_profit,
            expected_gross_profit=expected_profit,
            booked_margin_rate=booked_margin,
            expected_margin_rate=expected_margin,
            quote_to_order_rate=quote_to_order,
            reasons=tuple(reasons),
            next_actions=tuple(next_actions),
        )

    def write(self, summary: EconomicSummary, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "economic_outcome": asdict(summary)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
