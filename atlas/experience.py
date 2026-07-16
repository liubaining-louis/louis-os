from __future__ import annotations

import json
from typing import Any

from .memory import create_memory


def record_mission_experience(
    *,
    mission_id: str,
    mission_type: str,
    objective: str,
    status: str,
    workflow: str,
    risk_level: str,
    revision_count: int,
    provider: str,
    model: str,
    latency_ms: int,
    context: dict[str, Any],
) -> str | None:
    """Persist a compact reusable outcome without storing prompts, secrets or full reports."""
    if status not in {"completed", "failed_validation", "approval_required"}:
        return None

    domain = str(context.get("domain", mission_type or "general")).strip().casefold() or "general"
    confidence = 0.9 if status == "completed" else 0.65
    summary = {
        "mission_id": mission_id,
        "objective": objective[:500],
        "status": status,
        "workflow": workflow,
        "risk_level": risk_level,
        "revision_count": revision_count,
        "provider": provider,
        "model": model,
        "latency_ms": latency_ms,
    }
    record = create_memory(
        memory_type="outcome",
        domain=domain,
        content=json.dumps(summary, ensure_ascii=False, sort_keys=True),
        confidence=confidence,
        tags=["mission-experience", status, workflow],
        source="louis-os:auto-evaluation",
    )
    return record.memory_id
