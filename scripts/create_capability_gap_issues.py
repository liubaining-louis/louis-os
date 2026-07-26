#!/usr/bin/env python3
"""Create bounded internal capability issues from universal market evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
RECEIPTS_PATH = RESULTS / "capability_issue_receipts.json"
MAX_ISSUES_PER_CYCLE = 2


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def run_gh(args: list[str]) -> str:
    env = dict(os.environ)
    if not env.get("GH_TOKEN") and env.get("GITHUB_TOKEN"):
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def existing_issue_url(repo: str, marker: str) -> str | None:
    output = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--search",
            f'"{marker}" in:body',
            "--limit",
            "1",
            "--json",
            "url,body",
        ]
    )
    rows = json.loads(output or "[]")
    for row in rows:
        if marker in str(row.get("body") or ""):
            return str(row.get("url") or "")
    return None


def main() -> int:
    repo = os.getenv("GITHUB_REPOSITORY", "liubaining-louis/louis-os")
    backlog = load_json(BACKLOG_PATH, {"items": []})
    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    known = {str(item.get("marker")) for item in receipts.get("receipts", []) if item.get("marker")}
    created_this_cycle = 0
    deferred_this_cycle = 0

    for item in backlog.get("items", []):
        if created_this_cycle >= MAX_ISSUES_PER_CYCLE:
            break
        if not isinstance(item, dict):
            continue
        if item.get("deferred_by_cash_first"):
            deferred_this_cycle += 1
            continue
        issue = item.get("issue")
        if not isinstance(issue, dict):
            continue
        marker = str(issue.get("marker") or "")
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        if not marker or not title or marker not in body:
            continue
        if marker in known:
            continue
        try:
            url = existing_issue_url(repo, marker)
            status = "already_exists"
            if not url:
                url = run_gh(
                    [
                        "issue",
                        "create",
                        "--repo",
                        repo,
                        "--title",
                        title,
                        "--body",
                        body,
                    ]
                )
                status = "created"
                created_this_cycle += 1
            receipts.setdefault("receipts", []).append(
                {
                    "marker": marker,
                    "capability_id": item.get("capability_id"),
                    "execution_priority": item.get("execution_priority", "cash_first"),
                    "status": status,
                    "issue_url": url,
                    "source": str(BACKLOG_PATH.relative_to(ROOT)),
                }
            )
            known.add(marker)
        except Exception as exc:
            receipts.setdefault("receipts", []).append(
                {
                    "marker": marker,
                    "capability_id": item.get("capability_id"),
                    "execution_priority": item.get("execution_priority", "cash_first"),
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "source": str(BACKLOG_PATH.relative_to(ROOT)),
                }
            )
    receipts["updated_from_backlog"] = backlog.get("generated_at")
    receipts["created_this_cycle"] = created_this_cycle
    receipts["strategic_deferred_this_cycle"] = deferred_this_cycle
    receipts["policy"] = "cash-first capability issues only until a verified payment exists"
    save_json(RECEIPTS_PATH, receipts)
    print(
        json.dumps(
            {
                "created": created_this_cycle,
                "deferred": deferred_this_cycle,
                "receipts": len(receipts.get("receipts", [])),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
