from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .autonomous import ActionBudget, CycleRecord, get_cycle_store, run_cycle
from .autonomous_observers import collect_observations


def list_autonomous_cycles(limit: int = 20) -> list[dict[str, Any]]:
    return [record.to_dict() for record in get_cycle_store().list(limit=limit)]


def get_autonomous_cycle(cycle_id: str) -> dict[str, Any] | None:
    record = get_cycle_store().get(cycle_id)
    return record.to_dict() if record is not None else None


def run_autonomous_cycle(
    *,
    observation_key: str | None = None,
    pull_requests: list[dict[str, Any]] | None = None,
    deployments: list[dict[str, Any]] | None = None,
    mission_limit: int = 20,
    dry_run: bool = True,
    regression_detected: bool = False,
    approval_granted: bool = False,
    max_actions: int = 1,
    max_risk: float = 0.25,
    min_confidence: float = 0.65,
) -> CycleRecord:
    if mission_limit < 1 or mission_limit > 100:
        raise ValueError("mission_limit must be between 1 and 100")
    if max_actions < 0 or max_actions > 5:
        raise ValueError("max_actions must be between 0 and 5")
    if not 0.0 <= max_risk <= 1.0:
        raise ValueError("max_risk must be between 0 and 1")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")

    opportunities = collect_observations(
        pull_requests=pull_requests or [],
        deployments=deployments or [],
        mission_limit=mission_limit,
    )
    key = observation_key or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    return run_cycle(
        key,
        opportunities,
        get_cycle_store(),
        budget=ActionBudget(
            max_actions=max_actions,
            max_risk=max_risk,
            min_confidence=min_confidence,
        ),
        dry_run=dry_run,
        regression_detected=regression_detected,
        approval_granted=approval_granted,
    )
