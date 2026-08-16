#!/usr/bin/env python3
"""Promote a tested patch into a submission package only after policy validation."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.autonomous_submission import diagnose_submission_failure, validate_patch_manifest
from atlas.production_policy import evaluate_candidate, load_policy, preflight

RESULTS = ROOT / "results"
LEDGER_PATH = RESULTS / "monetization.json"
CANDIDATES_PATH = RESULTS / "monetization_candidates.json"
PACKAGE_PATH = RESULTS / "submission_package.json"
DIAGNOSIS_PATH = RESULTS / "submission_diagnosis.json"
POLICY_PATH = ROOT / "config" / "production_policy.json"

DISCOVERY_BLOCKERS = {
    "no_genuine_narrow_payable_candidate",
    "no_safe_convertible_payable_candidate",
    "no_final_safe_convertible_payable_candidate",
    "no_capability_matched_verified_payable_candidate",
    "production_policy_rejected_candidates",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _workspace_from_ledger(ledger: dict[str, Any]) -> Path | None:
    raw = str(ledger.get("current_execution_workspace") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        try:
            path = RESULTS / path.resolve().relative_to((ROOT / "results").resolve())
        except ValueError:
            return None
    elif path.parts and path.parts[0] == "results":
        path = ROOT / path
    else:
        path = RESULTS / path
    return path


def _candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "candidate_id", "title", "description", "reward_amount", "reward_usd_equivalent",
        "reward_verified", "payment_path", "payment_methods", "payment_evidence", "estimated_effort_hours",
        "effort_hours", "family", "task_family", "source_id", "source_url",
    )
    return {key: candidate.get(key) for key in keys if key in candidate}


def _find_candidate(candidate_id: str) -> dict[str, Any] | None:
    registry = load_json(CANDIDATES_PATH, {"candidates": []})
    for candidate in registry.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("id") or candidate.get("candidate_id") or "") == candidate_id:
            return candidate
    return None


def _record_policy_block(now: str, ledger: dict[str, Any], reason: str, candidate_id: str | None = None) -> int:
    diagnosis = {
        "generated_at": now,
        "status": "blocked",
        "blocked_stage": "production_policy_gate",
        "direct_cause": "The candidate cannot become an external submission package under the active owner policy.",
        "root_cause": reason,
        "root_cause_code": "production_policy_rejected_submission_package",
        "candidate_id": candidate_id,
        "resolution_class": "AUTO_RESOLVABLE",
        "next_action": "select_policy_compliant_quick_win_candidate",
        "human_intervention_minimal": "none",
    }
    save_json(DIAGNOSIS_PATH, diagnosis)
    if PACKAGE_PATH.exists():
        PACKAGE_PATH.unlink()
    ledger.update(
        {
            "updated_at": now,
            "execution_status": "production_policy_rejected_submission_package",
            "submission_blocked_stage": "production_policy_gate",
            "primary_blocker": reason,
            "next_action": "select_policy_compliant_quick_win_candidate",
        }
    )
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "blocked", "diagnosis": diagnosis}, ensure_ascii=False))
    return 0


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    ledger = load_json(LEDGER_PATH, {})
    policy = load_policy(POLICY_PATH)
    global_gate = preflight(policy)
    if not global_gate.allowed:
        return _record_policy_block(now, ledger, global_gate.reason)

    root_cause = str(ledger.get("root_cause_code") or "").strip()
    if root_cause in DISCOVERY_BLOCKERS and not ledger.get("top_opportunity"):
        diagnosis = {
            "status": "blocked",
            "blocked_stage": "opportunity_discovery",
            "direct_cause": "No candidate reached the patch workspace stage.",
            "root_cause": ledger.get("primary_blocker")
            or "The final opportunity discovery gate produced no safe convertible payable candidate.",
            "root_cause_code": root_cause,
            "resolution_class": "AUTO_RESOLVABLE",
            "next_action": ledger.get("next_action") or "refresh_capability_specific_verified_sources",
            "human_intervention_minimal": "none",
            "upstream_root_cause_preserved": True,
        }
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis})
        ledger.update(
            {
                "updated_at": now,
                "execution_status": root_cause,
                "submission_blocked_stage": "opportunity_discovery",
                "downstream_package_stage": "skipped_no_candidate",
                "upstream_root_cause_preserved": True,
            }
        )
        save_json(LEDGER_PATH, ledger)
        if PACKAGE_PATH.exists():
            PACKAGE_PATH.unlink()
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis}, ensure_ascii=False))
        return 0

    workspace = _workspace_from_ledger(ledger)
    if workspace is None or not workspace.is_dir():
        diagnosis = {
            "status": "blocked",
            "blocked_stage": "patch_workspace",
            "direct_cause": "No current execution workspace is available.",
            "root_cause": "A selected candidate has not yet produced a target-repository implementation workspace.",
            "resolution_class": "AUTO_RESOLVABLE",
            "next_action": "select_verified_candidate_and_create_target_repository_workspace",
            "human_intervention_minimal": "none",
        }
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis})
        ledger.update({"updated_at": now, "execution_status": "patch_workspace_missing", "next_action": diagnosis["next_action"]})
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis}, ensure_ascii=False))
        return 0

    manifest_path = workspace / "patch_manifest.json"
    if not manifest_path.is_file():
        diagnosis = diagnose_submission_failure(ValueError("generic_deliverable_not_submittable")).to_dict()
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis, "workspace": str(workspace)})
        ledger.update({
            "updated_at": now,
            "execution_status": "generic_deliverable_requires_patch",
            "submission_blocked_stage": diagnosis["blocked_stage"],
            "next_action": diagnosis["next_action"],
        })
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis, "workspace": str(workspace)}, ensure_ascii=False))
        return 0

    try:
        manifest = load_json(manifest_path, {})
        verified_files = validate_patch_manifest(manifest, workspace)
    except Exception as exc:
        diagnosis = diagnose_submission_failure(exc).to_dict()
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis, "workspace": str(workspace)})
        ledger.update({
            "updated_at": now,
            "execution_status": diagnosis["status"],
            "submission_blocked_stage": diagnosis["blocked_stage"],
            "next_action": diagnosis["next_action"],
        })
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": diagnosis["status"], "diagnosis": diagnosis}, ensure_ascii=False))
        return 0

    candidate_id = str(manifest.get("candidate_id") or "")
    candidate = _find_candidate(candidate_id)
    if not candidate:
        return _record_policy_block(now, ledger, "submission_candidate_context_missing", candidate_id)
    decision = evaluate_candidate(candidate, policy)
    if not decision.allowed:
        return _record_policy_block(now, ledger, decision.reason, candidate_id)

    package = {
        "generated_at": now,
        "candidate_id": candidate_id,
        "workspace": workspace.relative_to(RESULTS).as_posix(),
        "manifest_path": manifest_path.relative_to(RESULTS).as_posix(),
        "verified_patch_files": [{"path": item["path"], "sha256": item["sha256"]} for item in verified_files],
        "production_policy_mode": policy.get("mode"),
        "production_policy_reason": decision.reason,
        "candidate_policy_context": _candidate_context(candidate),
        "status": "ready_for_autonomous_submission",
    }
    save_json(PACKAGE_PATH, package)
    ledger.update({
        "updated_at": now,
        "execution_status": "ready_for_autonomous_submission",
        "submission_candidate_id": candidate_id,
        "production_policy_mode": policy.get("mode"),
        "next_action": "submit_tested_patch_with_existing_github_identity",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "ready", "package": package}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
