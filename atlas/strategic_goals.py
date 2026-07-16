from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

GoalStatus = Literal["active", "paused", "completed", "abandoned"]
Direction = Literal["maximize", "minimize"]


@dataclass(frozen=True)
class StrategicGoal:
    goal_id: str
    title: str
    owner: str
    metric: str
    target: float
    current: float
    horizon: str
    priority: int = 50
    direction: Direction = "maximize"
    status: GoalStatus = "active"
    updated_at: str = ""
    abandoned_hypothesis: str | None = None

    def validate(self) -> None:
        if not self.goal_id.strip() or not self.title.strip():
            raise ValueError("goal_id and title are required")
        if not self.owner.strip() or not self.metric.strip() or not self.horizon.strip():
            raise ValueError("owner, metric and horizon are required")
        if not 0 <= self.priority <= 100:
            raise ValueError("priority must be between 0 and 100")
        if self.direction not in {"maximize", "minimize"}:
            raise ValueError("invalid direction")
        if self.status not in {"active", "paused", "completed", "abandoned"}:
            raise ValueError("invalid status")
        if self.status == "abandoned" and not self.abandoned_hypothesis:
            raise ValueError("abandoned goals require an audit reason")

    def progress(self) -> float:
        self.validate()
        if self.direction == "maximize":
            if self.target == 0:
                return 1.0 if self.current >= 0 else 0.0
            return max(0.0, min(1.0, self.current / self.target))
        if self.current <= self.target:
            return 1.0
        baseline = max(abs(self.current), 1.0)
        return max(0.0, min(1.0, 1.0 - ((self.current - self.target) / baseline)))

    def priority_score(self) -> float:
        status_weight = {"active": 1.0, "paused": 0.25, "completed": 0.0, "abandoned": 0.0}[self.status]
        return round(self.priority * (1.0 - self.progress()) * status_weight, 6)


class JsonlStrategicGoalStore:
    """Append-only, dependency-free strategic goal persistence for local and dry-run use."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _events(self) -> list[dict]:
        if not self.path.exists():
            return []
        events: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def list(self) -> list[StrategicGoal]:
        latest: dict[str, StrategicGoal] = {}
        for event in self._events():
            payload = event["goal"]
            latest[payload["goal_id"]] = StrategicGoal(**payload)
        return sorted(latest.values(), key=lambda goal: goal.goal_id)

    def get(self, goal_id: str) -> StrategicGoal | None:
        return next((goal for goal in self.list() if goal.goal_id == goal_id), None)

    def save(self, goal: StrategicGoal, *, event: str = "upsert") -> StrategicGoal:
        goal.validate()
        stamped = replace(goal, updated_at=datetime.now(timezone.utc).isoformat())
        previous = self.get(goal.goal_id)
        if previous == stamped:
            return stamped
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"event": event, "recorded_at": stamped.updated_at, "goal": asdict(stamped)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return stamped

    def update_progress(self, goal_id: str, current: float) -> StrategicGoal:
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        completed = (
            goal.direction == "maximize" and current >= goal.target
        ) or (
            goal.direction == "minimize" and current <= goal.target
        )
        return self.save(replace(goal, current=current, status="completed" if completed else goal.status), event="progress")

    def abandon(self, goal_id: str, reason: str) -> StrategicGoal:
        if not reason.strip():
            raise ValueError("abandon reason is required")
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        return self.save(replace(goal, status="abandoned", abandoned_hypothesis=reason), event="abandoned")


def reprioritize(goals: Iterable[StrategicGoal]) -> list[StrategicGoal]:
    return sorted(goals, key=lambda goal: (-goal.priority_score(), goal.goal_id))


def conflicting_goals(goals: Iterable[StrategicGoal]) -> list[tuple[str, str]]:
    active = [goal for goal in goals if goal.status == "active"]
    conflicts: list[tuple[str, str]] = []
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if left.metric == right.metric and left.direction != right.direction:
                conflicts.append(tuple(sorted((left.goal_id, right.goal_id))))
    return sorted(set(conflicts))
