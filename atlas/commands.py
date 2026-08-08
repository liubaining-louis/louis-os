from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import build_plan, validate_plan
from .evidence_grounding import evidence_gate_error
from .missions import run_mission
from .runner import ROOT
from .self_healing_monetization import run_self_healing_deliverable_cycle
from .vm_command_bus import delegate_superteam_to_vm


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
    execution_mode: str | None = None
    evidence: list[str] = field(default_factory=list)
    diagnosis: dict[str, Any] | None = None

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


def _normalized_order(order: str) -> str:
    return " ".join(order.casefold().replace("_", " ").replace("-", " ").split())


def _is_verified_deliverable_cycle(order: str) -> bool:
    normalized = _normalized_order(order)
    return normalized in {
        "execute verified monetization deliverable cycle",
        "execute the verified monetization deliverable cycle",
        "exécute le cycle vérifié de livrable de monétisation",
        "exécuter le cycle vérifié de livrable de monétisation",
    }


def _is_first_euro_closed_loop(order: str) -> bool:
    normalized = _normalized_order(order)
    economic_markers = ("first euro", "first €", "premier euro", "premier €", "paid mission", "mission payée", "mission paye", "monetization", "monétisation")
    execution_markers = ("execute now", "execute_now", "prepare then gate", "prepare_then_gate", "external submission", "soumission externe", "verified external submission", "first euro closed loop", "closed loop mission")
    return any(marker in normalized for marker in economic_markers) and any(marker.replace("_", " ") in normalized for marker in execution_markers)


def _is_superteam_crypto_closed_loop(order: str) -> bool:
    normalized = _normalized_order(order)
    if "deterministic superteam executor" in normalized:
        return True
    platform = any(
        marker in normalized
        for marker in (
            "superteam",
            "crypto bounty",
            "crypto paid",
            "crypto bounty discovery",
            "agent allowed",
            "agent only",
        )
    )
    action = any(
        marker in normalized
        for marker in (
            "execute",
            "submit",
            "submission",
            "soumission",
            "closed loop",
            "prepare then gate",
            "verified external submission",
        )
    )
    return platform and action


def _apply_deterministic_outcome(record: CommandRecord, outcome: dict[str, Any]) -> None:
    status = str(outcome.get("status", "failed"))
    evidence = outcome.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
        evidence = []
    if status == "completed" and not evidence:
        raise RuntimeError("execution_completed_without_evidence")
    if status not in {"completed", "blocked", "failed"}:
        raise RuntimeError(f"invalid_deterministic_execution_status:{status}")
    record.status = status
    record.execution_mode = str(outcome.get("execution_mode", "deterministic_internal_executor"))
    record.evidence = evidence
    diagnosis = outcome.get("diagnosis")
    record.diagnosis = diagnosis if isinstance(diagnosis, dict) else None
    record.result = json.dumps(outcome, ensure_ascii=False)
    if status == "failed":
        record.error = str(outcome.get("error") or outcome.get("reason") or "deterministic_execution_failed")
    elif status == "blocked":
        record.error = str(outcome.get("reason") or "deterministic_execution_blocked")


def create_command(order: str, context: dict[str, Any] | None = None, idempotency_key: str | None = None, source: str = "chatgpt") -> dict[str, Any]:
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
    record = CommandRecord(command_id=str(uuid.uuid4()), idempotency_key=key, created_at=now, updated_at=now, source=source.strip() or "unknown", order=order, context=context, status="received", plan=plan.to_dict())
    _save(record)
    if not valid:
        record.status = "failed"
        record.error = "; ".join(errors)
        _save(record)
        return record.to_dict()

    deterministic_superteam = _is_superteam_crypto_closed_loop(order)
    deterministic_first_euro = _is_first_euro_closed_loop(order)
    deterministic_route = deterministic_superteam or deterministic_first_euro
    if plan.requires_external_action and not deterministic_route:
        record.status = "approval_required"
        _save(record)
        return record.to_dict()
    evidence_error = evidence_gate_error(order, context)
    if evidence_error and not deterministic_route:
        record.status = "blocked"
        record.error = evidence_error
        _save(record)
        return record.to_dict()

    record.status = "running"
    _save(record)
    try:
        if deterministic_superteam:
            outcome = delegate_superteam_to_vm(record.command_id, order=order, context=context)
            _apply_deterministic_outcome(record, outcome)
        elif _is_verified_deliverable_cycle(order) or deterministic_first_euro:
            outcome = run_self_healing_deliverable_cycle(ROOT)
            _apply_deterministic_outcome(record, outcome)
        else:
            mission = run_mission(plan.mission_type, order, context)
            record.status = "completed"
            record.mission_id = mission.mission_id
            record.result = mission.result
            record.execution_mode = "generative_mission"
    except Exception as exc:
        record.status = "failed"
        record.error = f"{type(exc).__name__}: {exc}"
        record.diagnosis = {
            "symptom": "Command execution failed.", "blocked_stage": "command_execution", "direct_cause": record.error,
            "root_cause": "The selected command route raised an unhandled technical exception.", "confidence": 0.99,
            "resolution_class": "AUTO_RESOLVABLE", "correction": "Reproduce the error, add a regression test, correct the route and retry with a new idempotency key.",
            "validation_test": "the route returns completed with evidence or blocked with a causal diagnosis", "next_action": "open_targeted_regression_fix", "human_intervention_minimal": "none",
        }
    _save(record)
    return record.to_dict()
