from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

from atlas.experiment_planner import ExperimentPlan

ExperimentDecision = Literal["continue", "revise", "stop"]


@dataclass(frozen=True)
class ExperimentOutcome:
    experiment_id: str
    sample_size: int
    qualified_positive_count: int
    observed_cost_score: float
    observed_human_dependency: float
    evidence_references: tuple[str, ...]

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id is required")
        if self.sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if not 0 <= self.qualified_positive_count <= self.sample_size:
            raise ValueError("qualified_positive_count must be between zero and sample_size")
        for name in ("observed_cost_score", "observed_human_dependency"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not self.evidence_references:
            raise ValueError("outcome evidence references are required")

    @property
    def positive_intent_rate(self) -> float:
        return self.qualified_positive_count / self.sample_size


@dataclass(frozen=True)
class ExperimentEvaluation:
    experiment_id: str
    decision: ExperimentDecision
    observed_rate: float
    threshold: float
    reasons: tuple[str, ...]


class ExperimentOutcomeEvaluator:
    """Evaluate measured outcomes without allowing unsupported venture promotion."""

    def __init__(self, *, revision_margin: float = 0.05) -> None:
        if not 0 <= revision_margin <= 1:
            raise ValueError("revision_margin must be between 0 and 1")
        self.revision_margin = revision_margin

    def evaluate(self, plan: ExperimentPlan, outcome: ExperimentOutcome) -> ExperimentEvaluation:
        plan.validate()
        outcome.validate()
        if outcome.experiment_id != plan.experiment_id:
            raise ValueError("outcome experiment_id does not match plan")

        rate = outcome.positive_intent_rate
        reasons: list[str] = []
        if outcome.observed_cost_score > plan.maximum_cost_score:
            reasons.append("observed cost exceeded experiment gate")
        if outcome.observed_human_dependency > plan.maximum_human_dependency:
            reasons.append("observed human dependency exceeded experiment gate")
        if reasons:
            decision: ExperimentDecision = "stop"
        elif rate >= plan.success_threshold:
            decision = "continue"
            reasons.append("success threshold met")
        elif rate >= max(0.0, plan.success_threshold - self.revision_margin):
            decision = "revise"
            reasons.append("result is close enough to threshold for one bounded revision")
        else:
            decision = "stop"
            reasons.append("success threshold missed")

        return ExperimentEvaluation(
            experiment_id=plan.experiment_id,
            decision=decision,
            observed_rate=round(rate, 6),
            threshold=plan.success_threshold,
            reasons=tuple(reasons),
        )

    def write(self, evaluations: Iterable[ExperimentEvaluation], output_path: str | Path) -> str:
        items = list(evaluations)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "evaluation_count": len(items),
            "evaluations": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
