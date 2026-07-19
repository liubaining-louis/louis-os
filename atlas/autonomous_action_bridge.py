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

_APPROVAL_PATTERNS = (
    r"\b(oui|ok|d'accord|autorise|autorisation|valid[ée]?)\b",
    r"\b(tu peux|vas[- ]?y|lance|ex[ée]cute|fais[- ]?le)\b",
)
_GITHUB_MARKERS = ("github", "bounty", "prime", "issue", "pull request", "pr")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_explicit_github_approval(message: str) -> bool:
    text = message.casefold()
    approved = any(re.search(pattern, text, re.I) for pattern in _APPROVAL_PATTERNS)
    scoped = any(marker in text for marker in _GITHUB_MARKERS)
    return approved and scoped


def queue_approved_action(
    db: firestore.Client,
    *,
    session_id: str,
    message: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    top = state.get("top_candidate") or {}
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
        "target_url": top.get("url", ""),
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
