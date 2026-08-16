#!/usr/bin/env python3
"""Apply repository-admin controls without exposing the admin token.

This is an idempotent one-shot migration used by a GitHub Actions workflow. It
protects `main` while explicitly allowing GitHub Actions to bypass the branch
ruleset so existing H24 state-writer workflows keep functioning.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.github.com"
API_VERSION = "2026-03-10"
RULESET_NAME = "Louis OS protected main"
GITHUB_ACTIONS_APP_ID = 15368
REQUIRED_CHECKS = [
    "test-and-benchmark (3.11)",
    "test-and-benchmark (3.12)",
]


class AdminApiError(RuntimeError):
    pass


def request_json(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "louis-os-admin-hardening",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            body = json.loads(raw) if raw else {}
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"message": raw[:500]}
        status = int(exc.code)
    if status not in expected:
        message = body.get("message") if isinstance(body, dict) else None
        raise AdminApiError(f"GitHub admin API {method} {path} returned HTTP {status}: {message or 'request rejected'}")
    return status, body


def desired_ruleset() -> dict[str, Any]:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_id": GITHUB_ACTIONS_APP_ID,
                "actor_type": "Integration",
                "bypass_mode": "always",
            }
        ],
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["squash", "merge", "rebase"],
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "do_not_enforce_on_create": True,
                    "required_status_checks": [
                        {"context": context, "integration_id": GITHUB_ACTIONS_APP_ID}
                        for context in REQUIRED_CHECKS
                    ],
                    "strict_required_status_checks_policy": True,
                },
            },
        ],
    }


def apply_ruleset(token: str, repo: str) -> dict[str, Any]:
    _, existing = request_json(token, "GET", f"/repos/{repo}/rulesets")
    matches = [row for row in existing if isinstance(row, dict) and row.get("name") == RULESET_NAME]
    payload = desired_ruleset()
    if matches:
        ruleset_id = int(matches[0]["id"])
        _, result = request_json(
            token,
            "PUT",
            f"/repos/{repo}/rulesets/{ruleset_id}",
            payload,
        )
        action = "updated"
    else:
        _, result = request_json(
            token,
            "POST",
            f"/repos/{repo}/rulesets",
            payload,
            expected=(201,),
        )
        action = "created"
    return {
        "action": action,
        "id": result.get("id"),
        "name": result.get("name"),
        "enforcement": result.get("enforcement"),
    }


def apply_environment_policy(token: str, repo: str) -> dict[str, Any]:
    environment_name = urllib.parse.quote("production", safe="")
    _, env = request_json(
        token,
        "PUT",
        f"/repos/{repo}/environments/{environment_name}",
        {
            "wait_timer": 0,
            "prevent_self_review": False,
            "reviewers": [],
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
        },
    )
    _, policies = request_json(
        token,
        "GET",
        f"/repos/{repo}/environments/{environment_name}/deployment-branch-policies?per_page=100",
    )
    rows = policies.get("branch_policies", []) if isinstance(policies, dict) else []
    main = next((row for row in rows if row.get("name") == "main"), None)
    if main is None:
        _, main = request_json(
            token,
            "POST",
            f"/repos/{repo}/environments/{environment_name}/deployment-branch-policies",
            {"name": "main", "type": "branch"},
            expected=(200,),
        )
        action = "created_main_policy"
    else:
        action = "main_policy_present"
    return {
        "action": action,
        "environment": env.get("name"),
        "custom_branch_policies": (env.get("deployment_branch_policy") or {}).get("custom_branch_policies"),
        "main_policy_id": main.get("id") if isinstance(main, dict) else None,
    }


def verify(token: str, repo: str) -> dict[str, Any]:
    _, rulesets = request_json(token, "GET", f"/repos/{repo}/rulesets")
    ruleset = next((row for row in rulesets if row.get("name") == RULESET_NAME), None)
    if not ruleset or ruleset.get("enforcement") != "active":
        raise AdminApiError("ruleset verification failed")

    environment_name = urllib.parse.quote("production", safe="")
    _, env = request_json(token, "GET", f"/repos/{repo}/environments/{environment_name}")
    branch_config = env.get("deployment_branch_policy") or {}
    if branch_config.get("custom_branch_policies") is not True:
        raise AdminApiError("production custom deployment branch policy verification failed")
    _, policies = request_json(
        token,
        "GET",
        f"/repos/{repo}/environments/{environment_name}/deployment-branch-policies?per_page=100",
    )
    rows = policies.get("branch_policies", []) if isinstance(policies, dict) else []
    if not any(row.get("name") == "main" for row in rows):
        raise AdminApiError("production main deployment policy verification failed")
    return {
        "ruleset_active": True,
        "ruleset_name": RULESET_NAME,
        "production_custom_branch_policy": True,
        "production_main_only_policy_present": True,
        "github_actions_bypass_app_id": GITHUB_ACTIONS_APP_ID,
        "required_status_checks": REQUIRED_CHECKS,
    }


def main() -> int:
    token = os.getenv("GH_ADMIN_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise SystemExit("GH_ADMIN_TOKEN is missing; admin hardening was not applied")
    if "/" not in repo:
        raise SystemExit("GITHUB_REPOSITORY must be owner/name")

    try:
        ruleset = apply_ruleset(token, repo)
        environment = apply_environment_policy(token, repo)
        verified = verify(token, repo)
    except AdminApiError as exc:
        print(f"ADMIN_HARDENING_FAILED={exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "github_admin_hardening_verified",
        "ruleset": ruleset,
        "environment": environment,
        "verification": verified,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
