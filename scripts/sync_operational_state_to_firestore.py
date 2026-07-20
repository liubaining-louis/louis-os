#!/usr/bin/env python3
"""Synchronize the final monetization state to Firestore after every worker cycle.

The scout used to publish an early, preparation-only snapshot before approval,
execution and receipt steps had run. This synchronizer runs last and replaces the
runtime document with one canonical state derived from the committed result files.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.opportunity_readiness import candidate_is_executable

RESULTS = ROOT / "results"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")


def load_json(name: str, default: Any) -> Any:
    path = RESULTS / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def sanitize_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    cleaned = dict(candidate)
    cleaned["autonomy_policy"] = "result_first_autonomy"
    cleaned["manual_validation_required"] = not candidate_is_executable(cleaned)
    if cleaned["manual_validation_required"]:
        cleaned["manual_validation_reasons"] = list(
            cleaned.get("external_prerequisites") or ["execution_readiness_not_proven"]
        )
    return cleaned


def build_operational_state(now: str | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).isoformat()
    ledger = load_json("monetization.json", {})
    candidates = load_json("monetization_candidates.json", {"candidates": []})
    queue = load_json("external_action_queue.json", {"actions": []})
    receipts = load_json("external_action_receipts.json", {"receipts": []})

    actions = queue.get("actions") or []
    ready = [item for item in actions if item.get("status") == "ready"]
    prepared = [item for item in actions if item.get("status") == "prepared_pending_deliverable"]
    verified_receipts = [item for item in (receipts.get("receipts") or []) if item.get("verified")]

    candidate_items = candidates.get("candidates") or []
    executable_candidates = [item for item in candidate_items if candidate_is_executable(item)]
    gated_candidates = [item for item in candidate_items if not candidate_is_executable(item)]
    ledger_top = ledger.get("top_opportunity")
    top = ledger_top if candidate_is_executable(ledger_top or {}) else None
    if "top_opportunity" not in ledger and executable_candidates:
        top = executable_candidates[0]
    execution_status = ledger.get("execution_status") or "researching"
    next_action = ledger.get("next_action") or "Continue autonomous research and execution."

    if verified_receipts:
        execution_status = "external_action_verified"
        next_action = "Track the external response and verify revenue independently."
    elif ready:
        execution_status = "ready_for_autonomous_external_execution"
        next_action = "Execute the tested low-risk action and record a verifiable receipt."
    elif prepared:
        execution_status = "building_tested_deliverable"
        next_action = "Finish the deliverable, run tests and attach reproducible evidence."

    return {
        "schema_version": 2,
        "state_source": "results_final_cycle_sync",
        "autonomy_policy": "result_first_autonomy",
        "worker_status": "running",
        "worker_verified": True,
        "waiting_for_instruction": False,
        "human_gate_pending": False,
        "requires_user_validation": False,
        "execution_status": execution_status,
        "current_activity": next_action,
        "next_action": next_action,
        "top_candidate": sanitize_candidate(top),
        "opportunities_qualified": candidates.get("count", len(candidates.get("candidates") or [])),
        "opportunities_executable": len(executable_candidates),
        "opportunities_gated": len(gated_candidates),
        "internal_execution_actions": int(ledger.get("internal_execution_actions", 0)),
        "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)),
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)),
        "external_actions_ready": len(ready),
        "external_actions_prepared": len(prepared),
        "external_receipts_verified": len(verified_receipts),
        "last_external_action_receipt": ledger.get("last_external_action_receipt"),
        "current_execution_issue": ledger.get("current_execution_issue"),
        "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0)),
        "synced_at": now,
    }


def main() -> int:
    state = build_operational_state()
    db = firestore.Client(project=PROJECT_ID)
    # Replace, rather than merge, to remove obsolete preparation-era fields.
    db.collection("louis_runtime").document("current").set(state)
    # Publish a stable canonical alias for new web clients.
    db.collection("operational_state").document("current").set(state)
    print(json.dumps({"status": "synced", "execution_status": state["execution_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
