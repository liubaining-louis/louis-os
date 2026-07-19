#!/usr/bin/env python3
"""Consume explicit owner approvals from the master GitHub issue.

Accepted command in issue #77 comments:
    /atlas approve top
    /atlas approve <candidate_id>

Only comments authored by the repository owner are accepted. Approvals are
persisted locally and later consumed exactly once by the opportunity executor.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CANDIDATES_PATH = RESULTS / "monetization_candidates.json"
APPROVALS_PATH = RESULTS / "action_approvals.json"
COMMAND_RE = re.compile(r"^\s*/atlas\s+approve\s+(top|[a-f0-9]{16})\s*$", re.I)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def github_get(url: str) -> Any:
    token = os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "louis-os-approval-manager",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def resolve_candidate(command_target: str, candidates: list[dict[str, Any]]) -> str | None:
    if command_target.lower() == "top":
        return str(candidates[0].get("id")) if candidates else None
    return command_target.lower()


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    owner = repository.split("/", 1)[0].lower()
    issue_number = int(os.getenv("ATLAS_APPROVAL_ISSUE", "77"))
    candidates = (load_json(CANDIDATES_PATH, {}).get("candidates") or [])
    valid_ids = {str(item.get("id")) for item in candidates}
    store = load_json(APPROVALS_PATH, {"approvals": []})
    seen_comments = {item.get("source_comment_id") for item in store.get("approvals", [])}
    comments = github_get(f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments?per_page=100")
    created = []
    now = datetime.now(timezone.utc).isoformat()

    for comment in comments:
        comment_id = comment.get("id")
        if comment_id in seen_comments:
            continue
        if str((comment.get("user") or {}).get("login", "")).lower() != owner:
            continue
        match = COMMAND_RE.match(str(comment.get("body") or ""))
        if not match:
            continue
        candidate_id = resolve_candidate(match.group(1), candidates)
        if not candidate_id or candidate_id not in valid_ids:
            continue
        approval = {
            "candidate_id": candidate_id,
            "status": "approved",
            "approved_at": now,
            "approved_by": owner,
            "scope": "internal_execution_and_tested_deliverable",
            "source": "github_issue_comment",
            "source_issue": issue_number,
            "source_comment_id": comment_id,
            "consumed_at": None,
        }
        store.setdefault("approvals", []).append(approval)
        seen_comments.add(comment_id)
        created.append(approval)

    store["updated_at"] = now
    save_json(APPROVALS_PATH, store)
    print(json.dumps({"status": "processed", "approvals_created": len(created), "approvals": created}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
