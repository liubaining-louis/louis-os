#!/usr/bin/env python3
"""Advance approved Louis OS actions only after the global production policy passes."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from atlas.production_policy import evaluate_candidate, load_policy, preflight

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
POLICY_PATH = os.getenv("LOUIS_PRODUCTION_POLICY", "config/production_policy.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _github_issue(url: str) -> dict[str, Any]:
    parts = url.rstrip("/").split("/")
    if len(parts) < 7 or parts[-2] != "issues":
        raise ValueError("Unsupported GitHub issue URL")
    owner, repo, number = parts[-4], parts[-3], parts[-1]
    api = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-autonomous-action-executor",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=30) as response:
        return json.load(response)


def _policy_candidate(action: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": issue.get("title", ""),
        "description": issue.get("body", ""),
        "reward_amount": action.get("reward_amount", action.get("reward_hint")),
        "reward_verified": action.get("reward_verified"),
        "payment_path": action.get("payment_path"),
        "effort_hours": action.get("estimated_effort_hours", action.get("effort_hours")),
        "family": action.get("family", action.get("task_family", "")),
    }


@firestore.transactional
def _claim_if_ready(transaction: Any, reference: Any) -> bool:
    snapshot = reference.get(transaction=transaction)
    action = snapshot.to_dict() or {}
    if action.get("status") != "approved_ready":
        return False
    transaction.set(
        reference,
        {
            "status": "planning_claimed",
            "claimed_at": _now(),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return True


def process_once() -> dict[str, Any]:
    policy = load_policy(POLICY_PATH)
    global_gate = preflight(policy)
    if not global_gate.allowed:
        raise RuntimeError(f"production_policy_blocked:{global_gate.reason}")

    db = firestore.Client(project=PROJECT_ID)
    docs = (
        db.collection("louis_action_queue")
        .where("status", "==", "approved_ready")
        .limit(5)
        .stream()
    )
    processed: list[str] = []
    policy_rejected: list[str] = []
    errors: list[str] = []
    for doc in docs:
        action = doc.to_dict() or {}
        action_id = doc.id
        target = str(action.get("target_url", ""))
        try:
            if not _claim_if_ready(db.transaction(), doc.reference):
                continue
            issue = _github_issue(target)
            current = doc.reference.get().to_dict() or {}
            if current.get("status") == "cancelled":
                continue

            decision = evaluate_candidate(_policy_candidate(action, issue), policy)
            if not decision.allowed:
                doc.reference.set(
                    {
                        "status": "policy_rejected",
                        "policy_reason": decision.reason,
                        "current_phase": "production_policy_gate",
                        "next_action": "Return to opportunity discovery under the active owner strategy.",
                        "user_intervention_required": False,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
                policy_rejected.append(action_id)
                continue

            body = str(issue.get("body") or "")
            dossier = {
                "action_id": action_id,
                "owner": "louis_os",
                "target_url": target,
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "requirements_excerpt": body[:12000],
                "labels": [x.get("name", "") for x in issue.get("labels", [])],
                "production_policy_reason": decision.reason,
                "execution_plan": [
                    "Analyse the acceptance and submission rules.",
                    "Identify the target repository and required implementation surface.",
                    "Prepare a branch/workspace and implementation checklist.",
                    "Generate and test the implementation using the connected coding agent when available.",
                    "Prepare the pull request and external submission without returning the work to the user.",
                ],
                "status": "implementation_planning",
                "created_at": _now(),
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            db.collection("louis_execution_dossiers").document(action_id).set(dossier, merge=True)
            doc.reference.set(
                {
                    "status": "implementation_planning",
                    "current_phase": "requirements_inspected",
                    "next_action": "Prepare implementation workspace and coding-agent task.",
                    "user_intervention_required": False,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            db.collection("louis_runtime").document("current").set(
                {
                    "waiting_for_instruction": False,
                    "active_action_id": action_id,
                    "active_action_status": "implementation_planning",
                    "current_activity": "Preparing a policy-approved quick-win implementation.",
                    "next_action": "Prepare implementation workspace and coding-agent task.",
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            processed.append(action_id)
        except Exception as exc:
            errors.append(f"{action_id}: {type(exc).__name__}: {exc}")
            doc.reference.set(
                {
                    "status": "retryable_error",
                    "last_error": errors[-1],
                    "retry_after": _now(),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
    result = {
        "processed": processed,
        "policy_rejected": policy_rejected,
        "errors": errors,
        "production_policy_mode": policy.get("mode"),
        "timestamp": _now(),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    process_once()
