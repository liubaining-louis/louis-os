from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Literal

ScheduleDecision = Literal["launch", "defer", "cooldown", "stop", "blocked"]


@dataclass(frozen=True)
class MissionCandidate:
    mission_id: str
    priority_score: float
    allocated_budget: float
    expected_gross_profit: float
    economic_decision: Literal["stop", "hold", "continue", "accelerate"]
    active: bool = False
    consecutive_no_progress_cycles: int = 0
    last_started_at: str = ""

    def validate(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id is required")
        if not 0 <= self.priority_score <= 1:
            raise ValueError("priority_score must be between 0 and 1")
        if self.allocated_budget < 0 or self.expected_gross_profit < 0:
            raise ValueError("budget and expected gross profit cannot be negative")
        if self.consecutive_no_progress_cycles < 0:
            raise ValueError("consecutive_no_progress_cycles cannot be negative")


@dataclass(frozen=True)
class ScheduledMission:
    mission_id: str
    decision: ScheduleDecision
    rank: int
    reserved_budget: float
    reason: str


@dataclass(frozen=True)
class SchedulerResult:
    generated_at: str
    total_budget: float
    reserved_budget: float
    active_before: int
    launch_count: int
    items: tuple[ScheduledMission, ...]


class AutonomousMissionScheduler:
    """Select the next bounded missions without executing external side effects."""

    def __init__(
        self,
        *,
        maximum_concurrent_missions: int = 3,
        cooldown_seconds: int = 3600,
        maximum_no_progress_cycles: int = 3,
    ) -> None:
        if maximum_concurrent_missions <= 0:
            raise ValueError("maximum_concurrent_missions must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        if maximum_no_progress_cycles <= 0:
            raise ValueError("maximum_no_progress_cycles must be positive")
        self.maximum_concurrent_missions = maximum_concurrent_missions
        self.cooldown_seconds = cooldown_seconds
        self.maximum_no_progress_cycles = maximum_no_progress_cycles

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def schedule(
        self,
        candidates: Iterable[MissionCandidate],
        *,
        total_budget: float,
        now: datetime | None = None,
    ) -> SchedulerResult:
        if total_budget < 0:
            raise ValueError("total_budget cannot be negative")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        items = tuple(candidates)
        seen: set[str] = set()
        for item in items:
            item.validate()
            if item.mission_id in seen:
                raise ValueError("duplicate mission_id")
            seen.add(item.mission_id)

        active_before = sum(item.active for item in items)
        slots = max(0, self.maximum_concurrent_missions - active_before)
        remaining_budget = total_budget
        ranked = sorted(
            items,
            key=lambda item: (
                item.economic_decision != "accelerate",
                -item.expected_gross_profit,
                -item.priority_score,
                item.mission_id,
            ),
        )

        scheduled: list[ScheduledMission] = []
        launched = 0
        for rank, item in enumerate(ranked, start=1):
            if item.active:
                scheduled.append(ScheduledMission(item.mission_id, "defer", rank, 0.0, "mission already active"))
                continue
            if item.economic_decision == "stop":
                scheduled.append(ScheduledMission(item.mission_id, "stop", rank, 0.0, "economic feedback stopped mission"))
                continue
            if item.consecutive_no_progress_cycles >= self.maximum_no_progress_cycles:
                scheduled.append(ScheduledMission(item.mission_id, "stop", rank, 0.0, "no measurable progress across bounded cycles"))
                continue
            last_started = self._parse_time(item.last_started_at)
            if last_started is not None and (current - last_started).total_seconds() < self.cooldown_seconds:
                scheduled.append(ScheduledMission(item.mission_id, "cooldown", rank, 0.0, "mission is inside cooldown window"))
                continue
            if slots <= 0:
                scheduled.append(ScheduledMission(item.mission_id, "defer", rank, 0.0, "concurrency limit reached"))
                continue
            if item.allocated_budget <= 0 or item.allocated_budget > remaining_budget:
                scheduled.append(ScheduledMission(item.mission_id, "blocked", rank, 0.0, "insufficient bounded budget"))
                continue

            scheduled.append(ScheduledMission(item.mission_id, "launch", rank, item.allocated_budget, "highest eligible economic priority"))
            remaining_budget -= item.allocated_budget
            slots -= 1
            launched += 1

        reserved = round(total_budget - remaining_budget, 2)
        return SchedulerResult(
            generated_at=current.isoformat().replace("+00:00", "Z"),
            total_budget=round(total_budget, 2),
            reserved_budget=reserved,
            active_before=active_before,
            launch_count=launched,
            items=tuple(scheduled),
        )

    def write(self, result: SchedulerResult, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "mission_schedule": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
