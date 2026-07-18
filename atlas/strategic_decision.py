from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Iterable, Literal

DecisionStatus = Literal["proposed", "approval_required", "no_action"]
OutcomeStatus = Literal["pending", "validated", "rejected", "learned"]


@dataclass(frozen=True)
class RiskAssessment:
    technical: int = 0
    legal: int = 0
    commercial: int = 0
    reputational: int = 0
    safety: int = 0

    def validate(self) -> None:
        values = asdict(self).values()
        if any(value < 0 or value > 10 for value in values):
            raise ValueError("risk dimensions must be between 0 and 10")

    @property
    def maximum(self) -> int:
        self.validate()
        return max(asdict(self).values(), default=0)

    @property
    def total(self) -> int:
        self.validate()
        return sum(asdict(self).values())


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    goal_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    expected_value: float
    confidence: float
    effort: int
    token_cost: int
    monetary_cost: float
    reversibility: float
    information_gain: float
    risk: RiskAssessment
    requires_approval: bool = False

    def validate(self) -> None:
        if not self.action_id.strip():
            raise ValueError("action_id is required")
        if not self.goal_ids:
            raise ValueError("at least one goal_id is required")
        if not 0.0 <= self.expected_value <= 1.0:
            raise ValueError("expected_value must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.effort < 0 or self.token_cost < 0 or self.monetary_cost < 0:
            raise ValueError("cost values must be non-negative")
        if not 0.0 <= self.reversibility <= 1.0:
            raise ValueError("reversibility must be between 0 and 1")
        if not 0.0 <= self.information_gain <= 1.0:
            raise ValueError("information_gain must be between 0 and 1")
        self.risk.validate()

    def score(self) -> float:
        self.validate()
        benefit = (self.expected_value * self.confidence * 10.0) + (self.information_gain * 2.0)
        safety = self.reversibility * 2.0
        cost = (self.effort * 0.5) + (self.token_cost / 10000.0) + self.monetary_cost
        risk_penalty = self.risk.total * 0.25
        return round(benefit + safety - cost - risk_penalty, 6)


@dataclass(frozen=True)
class StrategicDecision:
    decision_id: str
    candidate_actions: tuple[CandidateAction, ...]
    recommended_action_id: str | None
    status: DecisionStatus
    reason: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class DecisionOutcome:
    decision_id: str
    status: OutcomeStatus
    observed_value: float | None = None
    notes: str = ""

    def validate(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id is required")
        if self.observed_value is not None and not 0.0 <= self.observed_value <= 1.0:
            raise ValueError("observed_value must be between 0 and 1")


def _decision_id(actions: Iterable[CandidateAction]) -> str:
    payload = [asdict(action) for action in sorted(actions, key=lambda item: item.action_id)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def select_strategic_action(
    actions: Iterable[CandidateAction],
    *,
    max_risk: int = 2,
    max_effort: int = 5,
    max_token_cost: int = 20000,
    max_monetary_cost: float = 5.0,
) -> StrategicDecision:
    if min(max_risk, max_effort, max_token_cost) < 0 or max_monetary_cost < 0:
        raise ValueError("budgets must be non-negative")

    normalized = tuple(sorted(actions, key=lambda item: item.action_id))
    for action in normalized:
        action.validate()

    decision_id = _decision_id(normalized)
    if not normalized:
        return StrategicDecision(decision_id, normalized, None, "no_action", "no candidates")

    evidenced = tuple(action for action in normalized if action.evidence_refs)
    if not evidenced:
        return StrategicDecision(decision_id, normalized, None, "no_action", "missing evidence")

    eligible = tuple(
        action
        for action in evidenced
        if action.effort <= max_effort
        and action.token_cost <= max_token_cost
        and action.monetary_cost <= max_monetary_cost
    )
    if not eligible:
        return StrategicDecision(decision_id, normalized, None, "no_action", "all candidates exceed budget")

    ranked = sorted(eligible, key=lambda item: (item.score(), item.confidence, item.action_id), reverse=True)
    selected = ranked[0]
    if selected.requires_approval or selected.risk.maximum > max_risk:
        return StrategicDecision(
            decision_id,
            normalized,
            selected.action_id,
            "approval_required",
            "selected candidate exceeds autonomous approval boundary",
        )

    return StrategicDecision(decision_id, normalized, selected.action_id, "proposed", "highest-value safe candidate")
