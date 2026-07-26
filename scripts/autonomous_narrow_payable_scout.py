#!/usr/bin/env python3
"""Refresh the registry with final-safe payable tasks convertible by current handlers."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.candidate_registry import persist_firestore_registry
from atlas.final_bounty_safety_gate import discover_final_safe_registry

RESULTS = ROOT / "results"
CANDIDATES_PATH = RESULTS / "monetization_candidates.json"
REPORT_PATH = RESULTS / "narrow_payable_scout.json"
LEDGER_PATH = RESULTS / "monetization.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    outcome = discover_final_safe_registry()
    registry = outcome.registry
    candidate_count = int(registry.get("count", 0) or 0)
    backlog_count = int(registry.get("credible_backlog_count", 0) or 0)
    report = {
        "generated_at": now,
        "status": "final_safe_convertible_candidates_found" if candidate_count else "no_final_safe_convertible_payable_candidate",
        **outcome.to_dict(),
    }
    save_json(CANDIDATES_PATH, registry)
    save_json(REPORT_PATH, report)

    firestore_error: str | None = None
    try:
        persist_firestore_registry(registry)
    except Exception as exc:
        firestore_error = f"{type(exc).__name__}: {exc}"
        report["firestore_persist_error"] = firestore_error
        save_json(REPORT_PATH, report)

    ledger = load_json(LEDGER_PATH, {})
    top = (registry.get("candidates") or [None])[0] if candidate_count else None
    ledger.update(
        {
            "updated_at": now,
            "execution_status": (
                "final_safe_convertible_candidates_ready"
                if candidate_count
                else "no_final_safe_convertible_payable_candidate"
            ),
            "root_cause_code": None if candidate_count else "no_final_safe_convertible_payable_candidate",
            "primary_blocker": (
                None
                if candidate_count
                else "No open provider-backed bounty is simultaneously safe after final context-exfiltration checks, uncrowded and supported by the current deterministic patch handlers."
            ),
            "corrective_action": (
                "Build and test the highest-ranked deterministic patch."
                if candidate_count
                else "Continue high-precision searches and expand provider coverage without weakening safety or evidence requirements."
            ),
            "narrow_payable_candidates": candidate_count,
            "safe_convertible_candidates": candidate_count,
            "credible_nonconvertible_backlog": backlog_count,
            "provider_backed_candidates": int(registry.get("provider_backed_candidates", 0) or 0),
            "scout_items_inspected": outcome.inspected,
            "scout_items_rejected": len(outcome.rejected),
            "top_opportunity": top,
            "firestore_candidate_registry_synced": firestore_error is None,
            "next_action": (
                "run_target_preflight_and_patch_builder"
                if candidate_count
                else "expand_verified_provider_sources_and_refresh"
            ),
        }
    )
    save_json(LEDGER_PATH, ledger)
    print(
        json.dumps(
            {
                "status": report["status"],
                "inspected": outcome.inspected,
                "qualified": outcome.qualified,
                "credible_backlog": backlog_count,
                "rejected": len(outcome.rejected),
                "top_candidate": top,
                "firestore_persist_error": firestore_error,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
