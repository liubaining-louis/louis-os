from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal

EvolutionDecision = Literal["propose", "implement", "promote", "rollback", "hold"]


@dataclass(frozen=True)
class EvolutionSignal:
    signal_id: str
    category: Literal["revenue", "quality", "reliability", "latency", "cost"]
    baseline: float
    candidate: float
    higher_is_better: bool = True
    weight: float = 1.0

    def validate(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("signal_id is required")
        if self.weight <= 0:
            raise ValueError("weight must be positive")

    @property
    def normalized_delta(self) -> float:
        denominator = abs(self.baseline) if self.baseline else 1.0
        raw = (self.candidate - self.baseline) / denominator
        return raw if self.higher_is_better else -raw


@dataclass(frozen=True)
class EvolutionProposal:
    proposal_id: str
    problem: str
    hypothesis: str
    change_scope: tuple[str, ...]
    reversible: bool
    estimated_risk: Literal["low", "medium", "high"]
    created_at: str

    def validate(self) -> None:
        if not self.proposal_id.strip() or not self.problem.strip() or not self.hypothesis.strip():
            raise ValueError("proposal_id, problem and hypothesis are required")
        if not self.change_scope:
            raise ValueError("change_scope cannot be empty")
        datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))


@dataclass(frozen=True)
class EvolutionEvaluation:
    proposal_id: str
    decision: EvolutionDecision
    weighted_improvement: float
    regressions: tuple[str, ...]
    rationale: str
    evaluated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ControlledEvolutionEngine:
    """Promote only reversible, tested changes with measurable net improvement."""

    def __init__(self, *, promotion_threshold: float = 0.02, max_high_risk_auto_actions: int = 0) -> None:
        if promotion_threshold < 0:
            raise ValueError("promotion_threshold must be non-negative")
        if max_high_risk_auto_actions < 0:
            raise ValueError("max_high_risk_auto_actions must be non-negative")
        self.promotion_threshold = promotion_threshold
        self.max_high_risk_auto_actions = max_high_risk_auto_actions

    def evaluate(
        self,
        proposal: EvolutionProposal,
        signals: Iterable[EvolutionSignal],
        *,
        tests_passed: bool,
        deterministic_checks_passed: bool,
    ) -> EvolutionEvaluation:
        proposal.validate()
        items = tuple(signals)
        for signal in items:
            signal.validate()

        now = datetime.now(timezone.utc).isoformat()
        if not proposal.reversible:
            return EvolutionEvaluation(
                proposal.proposal_id,
                "hold",
                0.0,
                ("change is not reversible",),
                "Self-evolution requires a rollback path before implementation.",
                now,
            )

        if proposal.estimated_risk == "high" and self.max_high_risk_auto_actions == 0:
            return EvolutionEvaluation(
                proposal.proposal_id,
                "hold",
                0.0,
                ("high-risk change requires owner approval",),
                "High-risk autonomous promotion is disabled.",
                now,
            )

        if not tests_passed or not deterministic_checks_passed:
            regressions = []
            if not tests_passed:
                regressions.append("test suite failed")
            if not deterministic_checks_passed:
                regressions.append("deterministic checks failed")
            return EvolutionEvaluation(
                proposal.proposal_id,
                "rollback",
                0.0,
                tuple(regressions),
                "A candidate that fails verification must be rolled back.",
                now,
            )

        if not items:
            return EvolutionEvaluation(
                proposal.proposal_id,
                "hold",
                0.0,
                ("no evaluation signals",),
                "No promotion is allowed without measurable evidence.",
                now,
            )

        total_weight = sum(signal.weight for signal in items)
        weighted_improvement = sum(signal.normalized_delta * signal.weight for signal in items) / total_weight
        regressions = tuple(signal.signal_id for signal in items if signal.normalized_delta < 0)

        if regressions:
            decision: EvolutionDecision = "rollback"
            rationale = "At least one guarded metric regressed; candidate must not be promoted."
        elif weighted_improvement >= self.promotion_threshold:
            decision = "promote"
            rationale = "Candidate passed verification and exceeded the promotion threshold."
        else:
            decision = "hold"
            rationale = "Candidate is safe but improvement is too small to justify promotion."

        return EvolutionEvaluation(
            proposal_id=proposal.proposal_id,
            decision=decision,
            weighted_improvement=round(weighted_improvement, 6),
            regressions=regressions,
            rationale=rationale,
            evaluated_at=now,
        )


def self_evolution_policy() -> dict[str, object]:
    return {
        "loop": ["detect", "propose", "implement", "test", "evaluate", "promote_or_rollback", "learn"],
        "promotion_rule": "promote only when tests pass, deterministic checks pass, no guarded metric regresses, and measured improvement exceeds threshold",
        "default_risk_policy": "low and medium risk changes may proceed only when reversible; high risk requires owner approval",
        "north_star": "increase verified autonomous revenue without reducing safety, reliability, or evidence quality",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
