#!/usr/bin/env python3
"""Create one idempotent, evidence-backed internal execution ticket."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.opportunity_readiness import candidate_is_executable

RESULTS = ROOT / "results"
CANDIDATES_PATH = RESULTS / "monetization_candidates.json"
RECEIPTS_PATH = RESULTS / "opportunity_execution_receipts.json"
APPROVALS_PATH = RESULTS / "action_approvals.json"
LEDGER_PATH = RESULTS / "monetization.json"
MIN_SCORE = float(os.getenv("ATLAS_EXECUTION_MIN_SCORE", "60"))


def github_request(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    token = os.environ["GITHUB_TOKEN"]
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "louis-os-safe-opportunity-executor",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_approval(store: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    for approval in reversed(store.get("approvals", [])):
        if (
            approval.get("candidate_id") == candidate_id
            and approval.get("status") == "approved"
            and not approval.get("consumed_at")
        ):
            return approval
    return None


def internal_authorization_mode(
    candidate: dict[str, Any], approval: dict[str, Any] | None
) -> str:
    """Authorize reversible internal work for candidates already proven executable.

    An explicit approval remains valid evidence when present, but it is no longer a
    prerequisite for creating the internal implementation ticket. External
    submission, payment, KYC, legal acceptance and account creation remain governed
    by their dedicated gates.
    """
    if not candidate_is_executable(candidate):
        raise ValueError("candidate_not_executable")
    return "explicit_owner_approval" if approval else "autonomous_executable_candidate"


def build_issue(
    candidate: dict[str, Any], approval: dict[str, Any] | None = None
) -> tuple[str, str]:
    marker = f"<!-- atlas-candidate:{candidate['id']} -->"
    title = f"[ATLAS execution] {candidate.get('title', 'Qualified opportunity')[:120]}"
    authorization_mode = internal_authorization_mode(candidate, approval)
    approval_lines = ""
    if approval:
        approval_lines = (
            f"- Approval source: issue #{approval.get('source_issue')} comment "
            f"`{approval.get('source_comment_id')}`\n"
            f"- Approved by: `{approval.get('approved_by')}`\n"
        )
    body = f"""{marker}
## Qualified opportunity

- Source: {candidate.get('url', '')}
- Score: {candidate.get('score', 0)}/100
- Reward hint: {candidate.get('reward_hint', 0)} {candidate.get('currency', 'unknown')}
- Candidate ID: `{candidate['id']}`
- Internal authorization: `{authorization_mode}`
{approval_lines}
## Autonomous execution scope

1. Verify the source is still open and the reward terms are authoritative.
2. Inspect the target repository and contribution rules.
3. Produce a technical solution plan and test strategy.
4. Implement and test a patch in an isolated branch when technically feasible.
5. Attach evidence before any third-party submission.

## Guardrails

- Internal analysis, implementation and testing may start because readiness is `executable_now` and external prerequisites are cleared.
- No third-party comment, claim, application or pull request without a tested deliverable and the applicable external-action policy.
- No account creation, KYC, legal acceptance, spending, credential escalation or revenue claim.
- External submission count remains zero until a verifiable external receipt exists.
"""
    return title, body


def main() -> int:
    payload = load_json(CANDIDATES_PATH, {})
    candidates = payload.get("candidates") or []
    now = datetime.now(timezone.utc).isoformat()
    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    known = {item.get("candidate_id") for item in receipts.get("receipts", [])}

    if not candidates:
        print(json.dumps({"status": "no_candidate"}))
        return 0

    candidate = next((item for item in candidates if candidate_is_executable(item)), None)
    if candidate is None:
        print(json.dumps({"status": "no_executable_candidate", "gated_candidates": len(candidates)}))
        return 0

    repository = os.environ["GITHUB_REPOSITORY"]
    candidate_id = str(candidate.get("id"))
    if float(candidate.get("score", 0)) < MIN_SCORE:
        print(json.dumps({"status": "below_threshold", "score": candidate.get("score", 0)}))
        return 0
    if candidate_id in known:
        print(json.dumps({"status": "already_executing", "candidate_id": candidate_id}))
        return 0

    approvals = load_json(APPROVALS_PATH, {"approvals": []})
    approval = find_approval(approvals, candidate_id)
    authorization_mode = internal_authorization_mode(candidate, approval)
    title, body = build_issue(candidate, approval)
    try:
        issue = github_request(
            "POST",
            f"https://api.github.com/repos/{repository}/issues",
            {"title": title, "body": body},
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub issue creation failed: HTTP {exc.code}: {detail}") from exc

    if approval:
        approval["consumed_at"] = now
        approval["consumed_by_action"] = "internal_execution_issue_created"
        approvals["updated_at"] = now
        save_json(APPROVALS_PATH, approvals)

    receipt = {
        "timestamp": now,
        "candidate_id": candidate_id,
        "candidate_url": candidate.get("url"),
        "action": "internal_execution_issue_created",
        "authorization_mode": authorization_mode,
        "issue_number": issue.get("number"),
        "issue_url": issue.get("html_url"),
        "approval_comment_id": approval.get("source_comment_id") if approval else None,
        "external_submission": False,
        "revenue_evidence": False,
    }
    receipts.setdefault("receipts", []).append(receipt)
    receipts["updated_at"] = now
    save_json(RECEIPTS_PATH, receipts)

    ledger = load_json(LEDGER_PATH, {})
    ledger.update({
        "updated_at": now,
        "internal_execution_actions": int(ledger.get("internal_execution_actions", 0)) + 1,
        "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)),
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)),
        "current_execution_issue": issue.get("html_url"),
        "execution_status": "autonomous_execution_started",
        "internal_authorization_mode": authorization_mode,
        "approval_consumed": bool(approval),
        "approval_required_for_candidate": None,
        "next_action": "Produce, test and evidence the smallest deliverable before any external submission.",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "executing", **receipt}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
