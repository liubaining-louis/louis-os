from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

UNSAFE_ACTIONS = {
    "secret_change",
    "iam_change",
    "payment",
    "send_email",
    "purchase",
    "delete",
    "destructive_operation",
    "direct_merge",
}


@dataclass(frozen=True)
class Opportunity:
    id: str
    title: str
    impact: float
    urgency: float
    confidence: float
    effort: float
    risk: float
    action_type: str = "analysis"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionBudget:
    max_actions: int = 1
    max_risk: float = 0.25
    min_confidence: float = 0.65


@dataclass
class CycleRecord:
    cycle_id: str
    timestamp: str
    status: str
    dry_run: bool
    selected_opportunity: dict[str, Any] | None
    score: float | None
    stages: list[str]
    reason: str | None = None
    promoted: bool = False
    evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CycleStore(Protocol):
    def get(self, cycle_id: str) -> CycleRecord | None: ...

    def save(self, record: CycleRecord) -> None: ...


class JsonlCycleStore:
    """Local persistence used by tests and development.

    Production can provide a Firestore adapter implementing CycleStore without
    changing the autonomous loop.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, cycle_id: str) -> CycleRecord | None:
        if not self.path.exists():
            return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            data = json.loads(line)
            if data["cycle_id"] == cycle_id:
                return CycleRecord(**data)
        return None

    def save(self, record: CycleRecord) -> None:
        if self.get(record.cycle_id) is not None:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


def score_opportunity(opportunity: Opportunity) -> float:
    """Return a deterministic score in [0, 1]."""

    benefit = 0.45 * opportunity.impact + 0.25 * opportunity.urgency + 0.30 * opportunity.confidence
    penalty = 0.55 * opportunity.effort + 0.45 * opportunity.risk
    return round(max(0.0, min(1.0, benefit - 0.5 * penalty)), 6)


def make_cycle_id(observation_key: str, opportunities: Iterable[Opportunity]) -> str:
    payload = {
        "observation_key": observation_key,
        "opportunities": [asdict(item) for item in sorted(opportunities, key=lambda item: item.id)],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:20]


def run_cycle(
    observation_key: str,
    opportunities: Iterable[Opportunity],
    store: CycleStore,
    *,
    budget: ActionBudget | None = None,
    dry_run: bool = True,
    regression_detected: bool = False,
    approval_granted: bool = False,
) -> CycleRecord:
    """Execute one idempotent Observe → Learn cycle.

    The loop is deliberately conservative: one action maximum by default,
    dry-run by default, deterministic ranking and explicit stop conditions.
    """

    budget = budget or ActionBudget()
    candidates = list(opportunities)
    cycle_id = make_cycle_id(observation_key, candidates)
    existing = store.get(cycle_id)
    if existing is not None:
        return existing

    stages = ["observe"]
    eligible = [
        item
        for item in candidates
        if item.confidence >= budget.min_confidence and item.risk <= budget.max_risk
    ]
    ranked = sorted(eligible, key=lambda item: (-score_opportunity(item), item.id))
    selected = ranked[0] if ranked and budget.max_actions > 0 else None
    stages.append("prioritize")

    if selected is None:
        record = CycleRecord(
            cycle_id=cycle_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="stopped",
            dry_run=dry_run,
            selected_opportunity=None,
            score=None,
            stages=stages + ["learn"],
            reason="no_eligible_opportunity_or_budget_exhausted",
        )
        store.save(record)
        return record

    stages.append("plan")
    if selected.action_type in UNSAFE_ACTIONS and not approval_granted:
        record = CycleRecord(
            cycle_id=cycle_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="approval_required",
            dry_run=dry_run,
            selected_opportunity=asdict(selected),
            score=score_opportunity(selected),
            stages=stages + ["learn"],
            reason="unsafe_action_requires_explicit_approval",
        )
        store.save(record)
        return record

    stages.append("simulate" if dry_run else "execute")
    stages.append("evaluate")
    promoted = not dry_run and not regression_detected
    status = "simulated" if dry_run else ("completed" if promoted else "blocked")
    reason = "regression_detected" if regression_detected else None
    record = CycleRecord(
        cycle_id=cycle_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=status,
        dry_run=dry_run,
        selected_opportunity=asdict(selected),
        score=score_opportunity(selected),
        stages=stages + ["learn"],
        reason=reason,
        promoted=promoted,
        evaluation={"regression_detected": regression_detected},
    )
    store.save(record)
    return record
