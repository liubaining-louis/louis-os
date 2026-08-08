from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .superteam_crypto_cycle import run_superteam_crypto_cycle

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
COLLECTION = os.getenv("LOUIS_VM_COMMAND_COLLECTION", "louis_vm_commands")
TERMINAL = {"completed", "blocked", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    value = os.getenv("LOUIS_VM_COMMAND_BUS", os.getenv("LOUIS_LIVE_STATE_FIRESTORE", "1"))
    return str(value).strip().casefold() not in {"0", "false", "no", "off"}


def _db():
    from google.cloud import firestore

    return firestore.Client(project=PROJECT_ID)


def enqueue_vm_command(command_id: str, *, executor: str, order: str, context: dict[str, Any] | None = None) -> str:
    if not _enabled():
        raise RuntimeError("vm_command_bus_disabled")
    if not command_id.strip():
        raise ValueError("command_id is required")
    if executor not in {"superteam"}:
        raise ValueError(f"unsupported_vm_executor:{executor}")
    ref = _db().collection(COLLECTION).document(command_id)
    ref.set(
        {
            "schema_version": "1.0",
            "command_id": command_id,
            "executor": executor,
            "order": order,
            "context": context or {},
            "status": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "claimed_by": None,
            "outcome": None,
        },
        merge=True,
    )
    return f"firestore:{COLLECTION}/{command_id}"


def wait_for_vm_outcome(command_id: str, *, timeout_seconds: float = 55.0, poll_seconds: float = 1.5) -> dict[str, Any]:
    ref = _db().collection(COLLECTION).document(command_id)
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    while time.monotonic() < deadline:
        snapshot = ref.get()
        if snapshot.exists:
            payload = snapshot.to_dict() or {}
            if str(payload.get("status") or "") in TERMINAL:
                outcome = payload.get("outcome")
                if isinstance(outcome, dict):
                    evidence = list(outcome.get("evidence") or [])
                    queue_ref = f"firestore:{COLLECTION}/{command_id}"
                    if queue_ref not in evidence:
                        evidence.append(queue_ref)
                    outcome["evidence"] = evidence
                    return outcome
                return {
                    "status": "failed",
                    "execution_mode": "deterministic_superteam_executor",
                    "reason": "vm_command_terminal_without_outcome",
                    "diagnosis": {"blocked_stage": "vm_command_bus", "next_action": "inspect_vm_command_document"},
                    "evidence": [f"firestore:{COLLECTION}/{command_id}"],
                }
        time.sleep(max(0.2, poll_seconds))
    return {
        "status": "blocked",
        "execution_mode": "deterministic_superteam_executor",
        "reason": "vm_execution_timeout",
        "diagnosis": {"blocked_stage": "vm_command_bus", "next_action": "verify_vm_worker_queue_processing"},
        "evidence": [f"firestore:{COLLECTION}/{command_id}"],
    }


def delegate_superteam_to_vm(
    command_id: str,
    *,
    order: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    enqueue_vm_command(command_id, executor="superteam", order=order, context=context)
    timeout = timeout_seconds
    if timeout is None:
        timeout = float(os.getenv("LOUIS_VM_COMMAND_TIMEOUT_SECONDS", "55"))
    return wait_for_vm_outcome(command_id, timeout_seconds=timeout)


def _claim(ref, *, worker_id: str) -> dict[str, Any] | None:
    from google.cloud import firestore

    transaction = _db().transaction()

    @firestore.transactional
    def claim(txn):
        snapshot = ref.get(transaction=txn)
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        if payload.get("status") != "queued":
            return None
        txn.update(
            ref,
            {
                "status": "running",
                "claimed_by": worker_id,
                "claimed_at": _now(),
                "updated_at": _now(),
            },
        )
        return payload

    return claim(transaction)


def process_pending_vm_commands(root: Path, *, worker_id: str = "gcp_vm_monetization_worker", limit: int = 3) -> list[dict[str, Any]]:
    if not _enabled():
        return []
    db = _db()
    query = db.collection(COLLECTION).where("status", "==", "queued").limit(max(1, min(int(limit), 10)))
    processed: list[dict[str, Any]] = []
    for snapshot in query.stream():
        ref = snapshot.reference
        payload = _claim(ref, worker_id=worker_id)
        if payload is None:
            continue
        command_id = str(payload.get("command_id") or snapshot.id)
        executor = str(payload.get("executor") or "")
        try:
            if executor != "superteam":
                raise RuntimeError(f"unsupported_vm_executor:{executor}")
            outcome = run_superteam_crypto_cycle(root)
            status = str(outcome.get("status") or "failed")
            if status not in TERMINAL:
                raise RuntimeError(f"invalid_vm_outcome_status:{status}")
        except Exception as exc:
            status = "failed"
            outcome = {
                "status": "failed",
                "execution_mode": "deterministic_superteam_executor",
                "reason": f"{type(exc).__name__}: {exc}",
                "diagnosis": {"blocked_stage": "vm_executor", "next_action": "inspect_vm_worker_logs"},
                "evidence": [],
            }
        ref.update(
            {
                "status": status,
                "outcome": outcome,
                "finished_at": _now(),
                "updated_at": _now(),
            }
        )
        processed.append({"command_id": command_id, "status": status, "executor": executor})
    return processed
