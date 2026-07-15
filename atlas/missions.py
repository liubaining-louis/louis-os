from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .providers import complete
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


def run_mission(mission_type: str, objective: str, context: dict[str, Any]) -> MissionRecord:
    mission_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    prompt = (
        "You are executing a structured Louis OS mission.\n"
        f"Mission type: {mission_type}\n"
        f"Objective: {objective}\n"
        f"Context: {json.dumps(context, ensure_ascii=False)}\n\n"
        "Return a concise professional answer. Distinguish verified facts, assumptions, "
        "missing information, risks, and recommended next actions."
    )
    response = complete(prompt)
    latency_ms = int((time.perf_counter() - started) * 1000)
    completed_at = datetime.now(timezone.utc).isoformat()

    record = MissionRecord(
        mission_id=mission_id,
        created_at=created_at,
        completed_at=completed_at,
        mission_type=mission_type,
        objective=objective,
        context=context,
        status="completed",
        provider=response.provider,
        model=response.model,
        latency_ms=latency_ms,
        result=response.text,
    )

    get_mission_store().save(mission_id, asdict(record))
    return record


def get_mission(mission_id: str) -> dict[str, Any] | None:
    return get_mission_store().get(mission_id)


def list_missions(limit: int = 20) -> list[dict[str, Any]]:
    return get_mission_store().list(limit=limit)
