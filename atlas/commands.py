from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import build_plan, validate_plan
from .evidence_grounding import evidence_gate_error
from .missions import run_mission
from .runner import ROOT


@dataclass
class CommandRecord:
    command_id: str
    idempotency_key: str
    created_at: str
    updated_at: str
    source: str
    order: str
    context: dict[str, Any]
    status: str
    plan: dict[str, Any]
    mission_id: str | None = None
    result: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _local_dir() -> Path:
    return ROOT / "results" / "commands"


def _firestore_collection():
    from google.cloud import firestore

    client = firestore.Client()
    return client.collection(os.environ.get("FIRESTORE_COMMANDS_COLLECTION", "commands"))


def _save(record: CommandRecord) -> None:
    record.updated_at = datetime.now(timezone.utc).isoformat()
    payload = record.to_dict()
    if os.environ.get("COMMAND_STORE", "local") == "firestore":
        _firestore_collection().document(record.command_id).set(payload)
    else:
        path = _local_dir() / f"{record.command_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_command(command_id: str) -> dict[str, Any] | None:
    if os.environ.get("COMMAND_STORE", "local") == "firestore":
        snapshot = _firestore_collection().document(command_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    path = _local_dir() / f"{command_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_commands(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(int(limit), 1), 100)
    if os.environ.get("COMMAND_STORE", "local") == "firestore":
        docs = _firestore_collection().order_by("updated_at", direction="DESCENDING").limit(limit).stream()
        return [doc.to_dict() for doc in docs]
    directory = _local_dir()
    if not directory.exists():
        return []
    records = [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")]
    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return records[:limit]


def _find_by_idempotency_key(key: str) -> dict[str, Any] | None:
    if not key:
        return None
    if os.environ.get("COMMAND_STORE", "local") == "firestore":
        docs = _firestore_collection().where("idempotency_key", "==", key).limit(1).stream()
        for doc in docs:
            return doc.to_dict()
        return None
    for record in list_commands(limit=100):
        if record.get("idempotency_key") == key:
            return record
    return None


def create_command(
    order: str,
    context: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    source: str = "chatgpt",
) -> dict[str, Any]:
    order = order.strip()
    if not order:
        raise ValueError("order is required")
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise TypeError("context must be an object")

    key = (idempotency_key or str(uuid.uuid4())).strip()
    existing = _find_by_idempotency_key(key)
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    plan = build_plan(order, context)
    valid, errors = validate_plan(plan)
    record = CommandRecord(
        command_id=str(uuid.uuid4()),
        idempotency_key=key,
        created_at=now,
        updated_at=now,
        source=source.strip() or "unknown",
        order=order,
        context=context,
        status="received",
        plan=plan.to_dict(),
    )
    _save(record)

    if not valid:
        record.status = "failed"
        record.error = "; ".join(errors)
        _save(record)
        return record.to_dict()

    evidence_error = evidence_gate_error(order, context)
    if evidence_error:
        record.status = "blocked"
        record.error = evidence_error
        _save(record)
        return record.to_dict()

    if plan.requires_external_action:
        record.status = "approval_required"
        _save(record)
        return record.to_dict()

    record.status = "running"
    _save(record)
    try:
        mission = run_mission(plan.mission_type, order, context)
        record.status = "completed"
        record.mission_id = mission.mission_id
        record.result = mission.result
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
    _save(record)
    return record.to_dict()
