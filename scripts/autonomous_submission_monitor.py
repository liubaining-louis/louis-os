#!/usr/bin/env python3
"""Monitor submitted pull requests and persist the next autonomous action."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RECEIPTS_PATH = RESULTS / "submission_receipts.json"
MONITOR_PATH = RESULTS / "submission_monitor.json"
LEDGER_PATH = RESULTS / "monetization.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def github_get(path: str) -> Any:
    token = os.getenv("ATLAS_EXTERNAL_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("existing_github_credential_missing")
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "louis-os-submission-monitor",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_pr(url: str) -> tuple[str, str, int]:
    parts = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
    if len(parts) != 4 or parts[2] != "pull" or not parts[3].isdigit():
        raise ValueError("invalid_pull_request_url")
    return parts[0], parts[1], int(parts[3])


def derive_action(pr: dict[str, Any], reviews: list[dict[str, Any]], checks: list[dict[str, Any]]) -> tuple[str, str]:
    if pr.get("merged_at"):
        return "merged", "verify_reward_and_payout_status"
    if pr.get("state") == "closed":
        return "closed_without_merge", "diagnose_rejection_and_pivot_or_revise"
    requested_changes = [item for item in reviews if item.get("state") == "CHANGES_REQUESTED"]
    if requested_changes:
        return "changes_requested", "translate_maintainer_feedback_into_patch_revision"
    failed = [item for item in checks if item.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}]
    if failed:
        return "ci_failed", "fetch_logs_reproduce_fix_test_and_update_same_pull_request"
    pending = [item for item in checks if item.get("status") != "completed"]
    if pending:
        return "ci_pending", "wait_and_recheck_without_duplicate_submission"
    return "awaiting_maintainer", "monitor_without_spam_and_prepare_response_to_new_feedback"


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    ledger = load_json(LEDGER_PATH, {})
    latest = next((item for item in reversed(receipts.get("receipts", [])) if item.get("pull_request_url")), None)
    if not latest:
        result = {
            "generated_at": now,
            "status": "no_submission_to_monitor",
            "next_action": "build_and_submit_tested_repository_patch",
        }
        save_json(MONITOR_PATH, result)
        print(json.dumps(result))
        return 0

    owner, repo, number = parse_pr(str(latest["pull_request_url"]))
    pr = github_get(f"/repos/{owner}/{repo}/pulls/{number}")
    reviews = github_get(f"/repos/{owner}/{repo}/pulls/{number}/reviews")
    check_payload = github_get(f"/repos/{owner}/{repo}/commits/{pr['head']['sha']}/check-runs")
    checks = list(check_payload.get("check_runs") or [])
    status, next_action = derive_action(pr, list(reviews or []), checks)
    result = {
        "generated_at": now,
        "status": status,
        "pull_request_url": latest["pull_request_url"],
        "head_sha": pr.get("head", {}).get("sha"),
        "merged_at": pr.get("merged_at"),
        "review_count": len(reviews or []),
        "check_count": len(checks),
        "failed_checks": [item.get("html_url") for item in checks if item.get("conclusion") == "failure"],
        "next_action": next_action,
    }
    save_json(MONITOR_PATH, result)
    ledger.update({
        "updated_at": now,
        "execution_status": f"submission_{status}",
        "current_submission_url": latest["pull_request_url"],
        "next_action": next_action,
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
