"""Bridge explicit user approvals into an autonomous execution queue.

The bridge never treats approval as a request for the user to perform the work. It records
that Louis OS owns the task and lets a worker advance all software-executable phases.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

_APPROVAL_COMMAND = re.compile(
    r"^\s*AUTORISER\s+GITHUB\s+"
    r"(?P<target>[0-9a-f]{16}|https://github\.com/[^\s/]+/[^\s/]+/issues/\d+)\s*$",
    re.IGNORECASE,
)
_STOP_COMMAND = re.compile(
    r"^\s*(?:STOP|ARR(?:E|Ê)TE|ANNUL(?:E|ER)|R(?:E|É)VOQU(?:E|ER)|R(?:E|É)VOCATION)\b",
    re.IGNORECASE,
)
_ACTION_ID = re.compile(r"\b[0-9a-f]{32}\b", re.IGNORECASE)
_TERMINAL_STATUSES = {"cancelled", "completed", "failed", "external_submitted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def github_approval_target(message: str) -> str | None:
    """Return a target only for the canonical confirmation command."""

    match = _APPROVAL_COMMAND.fullmatch(message)
    return match.group("target") if match else None


def is_explicit_github_approval(message: str) -> bool:
    return github_approval_target(message) is not None


def stop_action_id(message: str) -> str | None:
    """Recognize stop/revocation before approval or model routing.

    A missing action id intentionally means "cancel every active action in this
    session". Stopping is broad and easy; approval is narrow and exact.
    """

    if not _STOP_COMMAND.match(message):
        return None
    match = _ACTION_ID.search(message)
    return match.group(0).lower() if match else "*"


def cancel_active_actions(
    db: firestore.Client,
    *,
    session_id: str,
    message: str,
    action_id: str | None = None,
) -> list[str]:
    now = _now()
    cancelled: list[str] = []
    docs = db.collection("louis_action_queue").where("session_id", "==", session_id).stream()
    for doc in docs:
        action = doc.to_dict() or {}
        if action_id and action_id != "*" and doc.id != action_id:
            continue
        if str(action.get("status", "")) in _TERMINAL_STATUSES:
            continue
        doc.reference.set(
            {
                "status": "cancelled",
                "cancelled_at": now,
                "cancellation_reason": message[:4000],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        cancelled.append(doc.id)

    if cancelled:
        db.collection("louis_runtime").document("current").set(
            {
                "waiting_for_instruction": True,
                "current_activity": "Stopped by an explicit user revocation.",
                "active_action_id": None,
                "active_action_status": "cancelled",
                "next_action": "Wait for a new, precisely scoped instruction.",
                "last_cancelled_action_ids": cancelled,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
    return cancelled


def queue_approved_action(
    db: firestore.Client,
    *,
    session_id: str,
    message: str,
    state: dict[str, Any],
    approved_target: str | None = None,
) -> dict[str, Any]:
    top = state.get("top_candidate") or {}
    candidate_id = str(top.get("id", ""))
    target_url = str(top.get("url", ""))
    approved_target = approved_target or github_approval_target(message)
    if not candidate_id or not target_url:
        raise ValueError("no_executable_candidate")
    if approved_target not in {candidate_id, target_url}:
        raise ValueError("approval_target_does_not_match_current_candidate")
    action_id = uuid.uuid4().hex
    now = _now()
    action = {
        "action_id": action_id,
        "kind": "execute_github_bounty",
        "status": "approved_ready",
        "owner": "louis_os",
        "user_intervention_required": False,
        "approval_scope": "Use the connected GitHub account for this candidate and perform all software-executable work.",
        "approval_text": message[:4000],
        "approved_at": now,
        "session_id": session_id,
        "candidate": top,
        "candidate_id": candidate_id,
        "target_url": target_url,
        "next_action": "Inspect requirements, create an implementation plan, prepare a working branch and advance execution without delegating the work back to the user.",
        "guardrails": {
            "allowed": ["read issue", "analyse requirements", "prepare code", "create branch", "run tests", "prepare PR"],
            "confirmation_still_required": ["payment", "KYC", "legal signature", "credential disclosure", "irreversible financial commitment"],
        },
        "created_at": now,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("louis_action_queue").document(action_id).set(action)
    db.collection("louis_runtime").document("current").set(
        {
            "waiting_for_instruction": False,
            "current_activity": "Executing the approved GitHub bounty as Louis OS owner.",
            "active_action_id": action_id,
            "active_action_status": "approved_ready",
            "next_action": action["next_action"],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return action
