#!/usr/bin/env python3
"""Advance approved Louis OS actions without delegating software work to the user."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")


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
    db = firestore.Client(project=PROJECT_ID)
    docs = (
        db.collection("louis_action_queue")
        .where("status", "==", "approved_ready")
        .limit(5)
        .stream()
    )
    processed: list[str] = []
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
            body = str(issue.get("body") or "")
            dossier = {
                "action_id": action_id,
                "owner": "louis_os",
                "target_url": target,
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "requirements_excerpt": body[:12000],
                "labels": [x.get("name", "") for x in issue.get("labels", [])],
                "execution_plan": [
                    "Analyse the bounty acceptance and submission rules.",
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
                    "current_activity": "Inspecting requirements and preparing the approved bounty implementation.",
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
    result = {"processed": processed, "errors": errors, "timestamp": _now()}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    process_once()
