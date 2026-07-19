#!/usr/bin/env python3
"""Execute one approved external GitHub action and record a verifiable receipt.

Supported v1 action: comment on an existing GitHub issue. The action is refused
unless the queue item is marked ready, has a tested deliverable and evidence,
and a matching unconsumed owner approval exists with scope external_submission.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
QUEUE_PATH = RESULTS / "external_action_queue.json"
APPROVALS_PATH = RESULTS / "action_approvals.json"
RECEIPTS_PATH = RESULTS / "external_action_receipts.json"
LEDGER_PATH = RESULTS / "monetization.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_external_approval(store: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    for approval in reversed(store.get("approvals", [])):
        if (
            approval.get("candidate_id") == candidate_id
            and approval.get("status") == "approved"
            and approval.get("scope") == "external_submission"
            and not approval.get("consumed_at")
        ):
            return approval
    return None


def validate_action(action: dict[str, Any]) -> tuple[bool, str]:
    required = ["id", "candidate_id", "type", "target_url", "body"]
    missing = [name for name in required if not action.get(name)]
    if missing:
        return False, f"missing_fields:{','.join(missing)}"
    if action.get("status") != "ready":
        return False, "not_ready"
    if action.get("type") != "github_issue_comment":
        return False, "unsupported_action_type"
    if action.get("tested_deliverable") is not True:
        return False, "deliverable_not_tested"
    evidence = action.get("evidence") or []
    if not isinstance(evidence, list) or not evidence:
        return False, "missing_evidence"
    parsed = urlparse(str(action["target_url"]))
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return False, "unsupported_target"
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "issues" or not parts[3].isdigit():
        return False, "invalid_github_issue_url"
    return True, "ok"


def issue_api_url(target_url: str) -> str:
    parts = [part for part in urlparse(target_url).path.split("/") if part]
    owner, repo, _, issue_number = parts
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"


def github_post(url: str, payload: dict[str, Any]) -> Any:
    token = os.getenv("ATLAS_EXTERNAL_GITHUB_TOKEN") or os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "louis-os-external-action-executor",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    queue = load_json(QUEUE_PATH, {"actions": []})
    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    completed_ids = {item.get("action_id") for item in receipts.get("receipts", [])}
    approvals = load_json(APPROVALS_PATH, {"approvals": []})

    action = next(
        (item for item in queue.get("actions", []) if item.get("id") not in completed_ids and item.get("status") == "ready"),
        None,
    )
    if not action:
        print(json.dumps({"status": "no_ready_external_action"}))
        return 0

    valid, reason = validate_action(action)
    if not valid:
        print(json.dumps({"status": "refused", "reason": reason, "action_id": action.get("id")}))
        return 0

    candidate_id = str(action["candidate_id"])
    approval = find_external_approval(approvals, candidate_id)
    if not approval:
        ledger = load_json(LEDGER_PATH, {})
        ledger.update({
            "updated_at": now,
            "execution_status": "awaiting_external_action_approval",
            "next_action": f"Add `/atlas approve external {candidate_id}` to issue #77.",
        })
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": "awaiting_external_approval", "candidate_id": candidate_id}))
        return 0

    try:
        response = github_post(issue_api_url(str(action["target_url"])), {"body": str(action["body"])})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"External GitHub action failed: HTTP {exc.code}: {detail}") from exc

    receipt = {
        "timestamp": now,
        "action_id": action["id"],
        "candidate_id": candidate_id,
        "action_type": action["type"],
        "target_url": action["target_url"],
        "receipt_url": response.get("html_url"),
        "receipt_id": response.get("id"),
        "approval_comment_id": approval.get("source_comment_id"),
        "evidence": action.get("evidence"),
        "verified": bool(response.get("html_url") and response.get("id")),
    }
    receipts.setdefault("receipts", []).append(receipt)
    receipts["updated_at"] = now
    save_json(RECEIPTS_PATH, receipts)

    approval["consumed_at"] = now
    approval["consumed_by_action"] = action["id"]
    approvals["updated_at"] = now
    save_json(APPROVALS_PATH, approvals)

    action["status"] = "submitted"
    action["submitted_at"] = now
    action["receipt_url"] = receipt["receipt_url"]
    queue["updated_at"] = now
    save_json(QUEUE_PATH, queue)

    ledger = load_json(LEDGER_PATH, {})
    ledger.update({
        "updated_at": now,
        "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)) + 1,
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)) + 1,
        "last_external_action_receipt": receipt["receipt_url"],
        "execution_status": "external_action_verified" if receipt["verified"] else "external_action_unverified",
        "next_action": "Track the external response and verify any resulting revenue independently.",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "external_action_verified", **receipt}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
