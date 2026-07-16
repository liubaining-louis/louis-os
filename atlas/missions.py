from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .experience import record_mission_experience
from .memory import retrieve_memories
from .orchestrator import orchestrate_mission
from .storage import get_mission_store


@dataclass
class MissionRecord:
    mission_id: str
    created_at: str
    completed_at: str
    mission_type: str
    objective: str
    context: dict[str, Any]
    status: str
    provider: str
    model: str
    latency_ms: int
    result: str
    memories_used: list[str]
    workflow: str
    risk_level: str
    requires_approval: bool
    revision_count: int
    traces: list[dict[str, Any]]
    experience_memory_id: str | None = None


def run_mission(mission_type: str, objective: str, context: dict[str, Any]) -> MissionRecord:
    mission_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    domain = str(context.get("domain", mission_type or "general")).strip().casefold()
    memories = retrieve_memories(objective, domain=domain, limit=5)
    orchestration = orchestrate_mission(mission_type, objective, context, memories)

    latency_ms = int((time.perf_counter() - started) * 1000)
    completed_at = datetime.now(timezone.utc).isoformat()
    record = MissionRecord(
        mission_id=mission_id,
        created_at=created_at,
        completed_at=completed_at,
        mission_type=orchestration.mission_type,
        objective=objective,
        context=context,
        status=orchestration.status,
        provider=orchestration.provider,
        model=orchestration.model,
        latency_ms=latency_ms,
        result=orchestration.final_answer,
        memories_used=[str(item.get("memory_id", "")) for item in memories if item.get("memory_id")],
        workflow=orchestration.workflow,
        risk_level=orchestration.risk_level,
        requires_approval=orchestration.requires_approval,
        revision_count=orchestration.revision_count,
        traces=[trace.to_dict() for trace in orchestration.traces],
    )

    try:
        record.experience_memory_id = record_mission_experience(
            mission_id=record.mission_id,
            mission_type=record.mission_type,
            objective=record.objective,
            status=record.status,
            workflow=record.workflow,
            risk_level=record.risk_level,
            revision_count=record.revision_count,
            provider=record.provider,
            model=record.model,
            latency_ms=record.latency_ms,
            context=record.context,
        )
    except (TypeError, ValueError, RuntimeError):
        # Experience capture must never turn a completed mission into a failed mission.
        record.experience_memory_id = None

    get_mission_store().save(mission_id, asdict(record))
    return record


def get_mission(mission_id: str) -> dict[str, Any] | None:
    return get_mission_store().get(mission_id)


def list_missions(limit: int = 20) -> list[dict[str, Any]]:
    return get_mission_store().list(limit=limit)
