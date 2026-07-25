#!/usr/bin/env python3
"""Create a concrete internal deliverable for the best verified candidate.

The command is fail-closed: it never submits externally and never increments
submission or revenue counters. It writes only reproducible internal evidence.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.deliverable_executor import execute_candidate

RESULTS = ROOT / "results"
WORKSPACES = RESULTS / "monetization_workspaces"


def load_candidates() -> list[dict]:
    path = RESULTS / "monetization_candidates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("candidates", []))


def select_candidate(candidates: list[dict]) -> dict | None:
    eligible = [
        item
        for item in candidates
        if item.get("readiness_status") == "executable_now"
        and item.get("external_prerequisites_cleared") is True
        and item.get("requires_user_validation") is False
        and item.get("authenticity_verified") is True
        and item.get("authenticity_status") in (None, "verified")
    ]
    eligible.sort(
        key=lambda item: (
            -float(item.get("execution_score", 0)),
            -float(item.get("score", 0)),
            str(item.get("id", "")),
        )
    )
    return eligible[0] if eligible else None


def update_ledger(receipt: dict | None, blocked_reason: str | None = None) -> None:
    path = RESULTS / "monetization.json"
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {}

    if receipt:
        ledger.update(
            {
                "execution_status": "deliverable_created",
                "current_execution_candidate": receipt["candidate_id"],
                "current_execution_workspace": receipt["workspace"],
                "current_execution_artifact": receipt["artifact_path"],
                "current_execution_artifact_sha256": receipt["artifact_sha256"],
                "internal_execution_actions": int(ledger.get("internal_execution_actions", 0)) + 1,
                "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)),
                "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)),
                "revenue_received": float(ledger.get("revenue_received", 0.0)),
                "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0)),
                "next_action": "Validate the concrete artifact against the authoritative acceptance criteria, then prepare a submission package.",
            }
        )
    else:
        ledger.update(
            {
                "execution_status": "no_eligible_verified_candidate",
                "execution_blocked_reason": blocked_reason or "no_candidate",
                "next_action": "Continue scouting until an authentic executable candidate exists.",
            }
        )
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    try:
        candidates = load_candidates()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        update_ledger(None, f"candidate_file_unavailable:{type(exc).__name__}")
        print(json.dumps({"status": "blocked", "reason": "candidate_file_unavailable"}))
        return 0

    candidate = select_candidate(candidates)
    if candidate is None:
        update_ledger(None, "no_authentic_executable_candidate")
        print(json.dumps({"status": "blocked", "reason": "no_authentic_executable_candidate"}))
        return 0

    receipt = asdict(execute_candidate(candidate, WORKSPACES))
    update_ledger(receipt)
    evidence_path = RESULTS / "evidence.jsonl"
    with evidence_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "internal_deliverable_created", **receipt}, ensure_ascii=False) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
