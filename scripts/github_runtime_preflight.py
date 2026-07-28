#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "github_runtime_contract.json"
RECEIPT = ROOT / "results" / "github_runtime_preflight.json"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    failures: list[str] = []
    if not token:
        failures.append("missing_github_token")
    if repository != contract["repository"]:
        failures.append("unexpected_or_missing_repository")

    authenticated = False
    issue_access = False
    if not failures:
        env = dict(os.environ)
        env["GH_TOKEN"] = token
        auth = subprocess.run(
            ["gh", "api", f"repos/{repository}"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        authenticated = auth.returncode == 0
        if not authenticated:
            failures.append("github_repository_api_unreachable")
        else:
            issue = subprocess.run(
                ["gh", "api", f"repos/{repository}/issues/{contract['master_issue']}"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            issue_access = issue.returncode == 0
            if not issue_access:
                failures.append("master_issue_unreachable")

    payload = {
        "schema_version": "1.0",
        "repository": repository,
        "master_issue": contract["master_issue"],
        "authenticated": authenticated,
        "master_issue_access": issue_access,
        "status": "ready" if not failures else "blocked",
        "failures": failures,
        "truth": {
            "prompt_grants_access": False,
            "runtime_preflight_required": True,
        },
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
