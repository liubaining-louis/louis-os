from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from atlas.venture_runtime import Opportunity


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    opportunity_id: str
    hypothesis: str
    target_customer: str
    proposed_offer: str
    method: tuple[str, ...]
    primary_metric: str
    success_threshold: float
    maximum_cost_score: float
    maximum_human_dependency: float
    evidence_references: tuple[str, ...]
    status: str = "planned"

    def validate(self) -> None:
        required = {
            "experiment_id": self.experiment_id,
            "opportunity_id": self.opportunity_id,
            "hypothesis": self.hypothesis,
            "target_customer": self.target_customer,
            "proposed_offer": self.proposed_offer,
            "primary_metric": self.primary_metric,
            "status": self.status,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing experiment plan fields: {', '.join(missing)}")
        if not self.method:
            raise ValueError("experiment method is required")
        if not self.evidence_references:
            raise ValueError("experiment evidence references are required")
        for name in ("success_threshold", "maximum_cost_score", "maximum_human_dependency"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


class OpportunityExperimentPlanner:
    """Turn accepted opportunities into bounded, measurable, non-executing experiment plans."""

    def __init__(
        self,
        *,
        minimum_success_threshold: float = 0.20,
        maximum_cost_score: float = 0.35,
        maximum_human_dependency: float = 0.30,
    ) -> None:
        for value, name in (
            (minimum_success_threshold, "minimum_success_threshold"),
            (maximum_cost_score, "maximum_cost_score"),
            (maximum_human_dependency, "maximum_human_dependency"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.minimum_success_threshold = minimum_success_threshold
        self.maximum_cost_score = maximum_cost_score
        self.maximum_human_dependency = maximum_human_dependency

    def plan(self, opportunity: Opportunity) -> ExperimentPlan:
        opportunity.validate()
        if opportunity.cost > self.maximum_cost_score:
            raise ValueError("opportunity cost exceeds experiment budget gate")
        if opportunity.human_dependency > self.maximum_human_dependency:
            raise ValueError("opportunity human dependency exceeds experiment gate")

        threshold = max(
            self.minimum_success_threshold,
            round(0.10 + 0.20 * opportunity.expected_value + 0.10 * opportunity.learning_value, 3),
        )
        plan = ExperimentPlan(
            experiment_id=f"exp-{opportunity.opportunity_id.removeprefix('opp-')}",
            opportunity_id=opportunity.opportunity_id,
            hypothesis=(
                f"If {opportunity.proposed_offer.strip()} is presented to "
                f"{opportunity.target_customer.strip()}, at least {threshold:.0%} of qualified targets "
                "will show measurable intent."
            ),
            target_customer=opportunity.target_customer.strip(),
            proposed_offer=opportunity.proposed_offer.strip(),
            method=(
                "define a bounded target sample from evidence-backed public data",
                "produce one minimal offer artifact without external publication",
                "simulate or stage the outreach workflow in dry-run mode",
                "record qualified-positive, neutral and negative outcomes",
                "compare the observed positive-intent rate with the success threshold",
            ),
            primary_metric="qualified_positive_intent_rate",
            success_threshold=threshold,
            maximum_cost_score=self.maximum_cost_score,
            maximum_human_dependency=self.maximum_human_dependency,
            evidence_references=tuple(sorted(set(opportunity.evidence_references))),
        )
        plan.validate()
        return plan

    def plan_many(self, opportunities: Iterable[Opportunity]) -> list[ExperimentPlan]:
        return [self.plan(opportunity) for opportunity in opportunities]

    def write(self, plans: Iterable[ExperimentPlan], output_path: str | Path) -> str:
        validated = list(plans)
        for plan in validated:
            plan.validate()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "experiment_count": len(validated),
            "experiments": [asdict(plan) for plan in validated],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
