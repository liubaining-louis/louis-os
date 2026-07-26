#!/usr/bin/env python3
"""Reject non-credible targets and build a real deterministic patch when supported."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.repository_patch_builder import build_patch_from_candidates

RESULTS = ROOT / "results"
CANDIDATES_PATH = RESULTS / "monetization_candidates.json"
LEDGER_PATH = RESULTS / "monetization.json"
PREFLIGHT_PATH = RESULTS / "target_preflight.json"
WORKSPACES = RESULTS / "target_repository_workspaces"


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
    registry = load_json(CANDIDATES_PATH, {"candidates": []})
    candidates = registry.get("candidates") or []
    result = build_patch_from_candidates(candidates, WORKSPACES)
    upstream_root_cause = str(registry.get("root_cause_code") or "").strip()
    upstream_empty = not candidates and bool(upstream_root_cause)

    payload = {"generated_at": now, **result.to_dict()}
    if upstream_empty:
        payload.update(
            {
                "status": "blocked",
                "diagnosis_code": upstream_root_cause,
                "blocked_stage": "opportunity_discovery",
                "upstream_root_cause_preserved": True,
                "inspected": registry.get("inspected"),
                "credible_backlog_count": registry.get("credible_backlog_count", 0),
            }
        )
    save_json(PREFLIGHT_PATH, payload)

    attempts_by_id = {str(item.get("candidate_id")): item for item in result.attempts if item.get("candidate_id")}
    for candidate in candidates:
        attempt = attempts_by_id.get(str(candidate.get("id")))
        if attempt:
            candidate["target_preflight_status"] = attempt.get("status")
            candidate["target_preflight_reasons"] = attempt.get("reasons", [])
            candidate["canonical_issue_url"] = attempt.get("canonical_issue_url")
            if attempt.get("status") == "rejected_noncredible_or_adversarial":
                candidate["status"] = "rejected_noncredible_or_adversarial"
                candidate["external_prerequisites_cleared"] = False
                candidate["requires_user_validation"] = False
    registry["updated_at"] = now
    registry["credible_candidates"] = sum(
        item.get("target_preflight_status") in {"credible_target", "credible_but_patch_not_built", "patch_built"}
        for item in candidates
    )
    registry["preflight_rejected"] = sum(
        item.get("target_preflight_status") == "rejected_noncredible_or_adversarial" for item in candidates
    )
    save_json(CANDIDATES_PATH, registry)

    ledger = load_json(LEDGER_PATH, {})
    if result.status == "patch_built":
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "target_repository_patch_built",
                "current_execution_candidate": result.candidate_id,
                "current_execution_workspace": result.workspace,
                "target_patch_manifest": result.manifest_path,
                "next_action": "validate_patch_manifest_and_submit_with_existing_github_identity",
            }
        )
    elif upstream_empty:
        ledger.update(
            {
                "updated_at": now,
                "execution_status": upstream_root_cause,
                "root_cause_code": upstream_root_cause,
                "primary_blocker": ledger.get("primary_blocker")
                or "No candidate survived the final safe-convertible opportunity discovery gate.",
                "corrective_action": ledger.get("corrective_action")
                or "Expand verified provider coverage and refresh high-precision searches.",
                "next_action": ledger.get("next_action") or "expand_verified_provider_sources_and_refresh",
                "downstream_patch_stage": "skipped_no_candidate",
                "upstream_root_cause_preserved": True,
            }
        )
    else:
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "candidate_pivot_required",
                "root_cause_code": result.diagnosis_code,
                "primary_blocker": "The candidate pool contains credible tasks outside the bounded patch handlers.",
                "corrective_action": "Add only the smallest deterministic handler justified by the highest-quality safe backlog task.",
                "next_action": "select_best_safe_backlog_task_for_bounded_handler_or_refresh",
            }
        )
    save_json(LEDGER_PATH, ledger)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
