from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any


class VentureState(str, Enum):
    OBSERVING = "observing"
    HYPOTHESIZING = "hypothesizing"
    SELECTED = "selected"
    BUILDING = "building"
    READY_FOR_TEST = "ready_for_test"
    APPROVAL_REQUIRED = "approval_required"
    TESTING = "testing"
    MEASURING = "measuring"
    LEARNING = "learning"
    SCALING = "scaling"
    PIVOTED = "pivoted"
    STOPPED = "stopped"


_ALLOWED_TRANSITIONS: dict[VentureState, set[VentureState]] = {
    VentureState.OBSERVING: {VentureState.HYPOTHESIZING, VentureState.STOPPED},
    VentureState.HYPOTHESIZING: {VentureState.SELECTED, VentureState.OBSERVING, VentureState.STOPPED},
    VentureState.SELECTED: {VentureState.BUILDING, VentureState.PIVOTED, VentureState.STOPPED},
    VentureState.BUILDING: {VentureState.READY_FOR_TEST, VentureState.PIVOTED, VentureState.STOPPED},
    VentureState.READY_FOR_TEST: {VentureState.APPROVAL_REQUIRED, VentureState.TESTING, VentureState.PIVOTED},
    VentureState.APPROVAL_REQUIRED: {VentureState.TESTING, VentureState.PIVOTED, VentureState.STOPPED},
    VentureState.TESTING: {VentureState.MEASURING, VentureState.STOPPED},
    VentureState.MEASURING: {VentureState.LEARNING, VentureState.STOPPED},
    VentureState.LEARNING: {VentureState.BUILDING, VentureState.SCALING, VentureState.PIVOTED, VentureState.STOPPED},
    VentureState.SCALING: {VentureState.MEASURING, VentureState.PIVOTED, VentureState.STOPPED},
    VentureState.PIVOTED: {VentureState.OBSERVING, VentureState.HYPOTHESIZING, VentureState.STOPPED},
    VentureState.STOPPED: set(),
}


@dataclass(frozen=True)
class VentureTransition:
    from_state: VentureState
    to_state: VentureState
    reason: str
    evidence_references: list[str]
    budget_delta: float = 0.0
    next_milestone: str = ""

    def validate(self) -> None:
        if self.to_state not in _ALLOWED_TRANSITIONS[self.from_state]:
            raise ValueError(f"invalid venture transition: {self.from_state} -> {self.to_state}")
        if not self.reason.strip():
            raise ValueError("transition reason is required")
        if not self.next_milestone.strip() and self.to_state not in {VentureState.STOPPED, VentureState.PIVOTED}:
            raise ValueError("next measurable milestone is required")
        if self.budget_delta < 0:
            raise ValueError("budget_delta must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VentureExperiment:
    experiment_id: str
    hypothesis: str
    action: str
    success_metric: str
    success_threshold: str
    deadline: str
    stop_condition: str
    budget_limit: float
    idempotency_key: str
    requires_approval: bool = True
    evidence_references: list[str] = field(default_factory=list)

    def validate(self) -> None:
        required = {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "action": self.action,
            "success_metric": self.success_metric,
            "success_threshold": self.success_threshold,
            "deadline": self.deadline,
            "stop_condition": self.stop_condition,
            "idempotency_key": self.idempotency_key,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing experiment fields: {', '.join(missing)}")
        if self.budget_limit < 0:
            raise ValueError("budget_limit must be non-negative")


@dataclass(frozen=True)
class ComparativeScore:
    evidence_grounding: int
    unsupported_claim_avoidance: int
    specificity: int
    feasibility: int
    autonomy_realism: int
    executable_artifacts: int
    measurable_next_action: int
    human_dependency: int
    learning_loop: int

    def total(self) -> int:
        return sum(asdict(self).values())


_UNSUPPORTED_PATTERNS = (
    re.compile(r"\$\s?\d[\d,]*(?:/year| per year|/month| per month)", re.IGNORECASE),
    re.compile(r"market size.{0,40}\$?\d", re.IGNORECASE),
    re.compile(r"growth potential.{0,20}\d+%", re.IGNORECASE),
    re.compile(r"client satisfaction.{0,20}\d+%", re.IGNORECASE),
)


def count_unsupported_numeric_claims(text: str, evidence_references: list[str] | None = None) -> int:
    refs = evidence_references or []
    count = sum(len(pattern.findall(text)) for pattern in _UNSUPPORTED_PATTERNS)
    return count if not refs else max(0, count - len(refs))


def promote_candidate(baseline: ComparativeScore, candidate: ComparativeScore, *, baseline_unsupported: int, candidate_unsupported: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if candidate.total() < baseline.total():
        reasons.append("aggregate comparative score regressed")
    if candidate_unsupported > baseline_unsupported:
        reasons.append("unsupported numeric claims increased")
    if candidate.evidence_grounding < baseline.evidence_grounding:
        reasons.append("evidence grounding regressed")
    if candidate.executable_artifacts == 0:
        reasons.append("candidate produced no executable artifact")
    return (not reasons, reasons)
