#!/usr/bin/env python3
"""Submit one tested repository patch only if the canonical production policy still allows it."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.autonomous_submission import diagnose_submission_failure, submit_patch
from atlas.production_policy import evaluate_candidate, load_policy, preflight

RESULTS = ROOT / "results"
PACKAGE_PATH = RESULTS / "submission_package.json"
RECEIPTS_PATH = RESULTS / "submission_receipts.json"
DIAGNOSIS_PATH = RESULTS / "submission_diagnosis.json"
LEDGER_PATH = RESULTS / "monetization.json"
POLICY_PATH = ROOT / "config" / "production_policy.json"

DISCOVERY_BLOCKERS = {
    "no_genuine_narrow_payable_candidate",
    "no_safe_convertible_payable_candidate",
    "no_final_safe_convertible_payable_candidate",
    "no_capability_matched_verified_payable_candidate",
    "production_policy_rejected_candidates",
    "production_policy_rejected_submission_package",
}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _policy_block(now: str, ledger: dict, reason: str, candidate_id: str | None = None) -> int:
    diagnosis = {
        "status": "blocked",
        "blocked_stage": "production_policy_gate",
        "direct_cause": "External pull-request submission is blocked by the active owner production policy.",
        "root_cause": reason,
        "root_cause_code": "production_policy_rejected_external_submission",
        "candidate_id": candidate_id,
        "resolution_class": "AUTO_RESOLVABLE",
        "next_action": "select_policy_compliant_quick_win_candidate",
        "human_intervention_minimal": "none",
    }
    save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis})
    ledger.update(
        {
            "updated_at": now,
            "execution_status": "production_policy_rejected_external_submission",
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
    package = load_json(PACKAGE_PATH, None)
    ledger = load_json(LEDGER_PATH, {})
    policy = load_policy(POLICY_PATH)
    global_gate = preflight(policy)
    if not global_gate.allowed:
        return _policy_block(now, ledger, global_gate.reason)

    root_cause = str(ledger.get("root_cause_code") or "").strip()

    if root_cause in DISCOVERY_BLOCKERS and not ledger.get("top_opportunity") and not isinstance(package, dict):
        diagnosis = {
            "status": "blocked",
            "blocked_stage": "opportunity_discovery",
            "direct_cause": "No submission package exists because no candidate survived discovery.",
            "root_cause": ledger.get("primary_blocker")
            or "The capability-first verified opportunity discovery gate produced no candidate.",
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
                "downstream_submitter_stage": "skipped_no_candidate",
                "upstream_root_cause_preserved": True,
            }
        )
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis}, ensure_ascii=False))
        return 0

    if not isinstance(package, dict):
        diagnosis = {
            "status": "blocked",
            "blocked_stage": "submission_package_loading",
            "direct_cause": "results/submission_package.json is missing or invalid.",
            "root_cause": "A selected candidate has not produced a tested repository patch package.",
            "resolution_class": "AUTO_RESOLVABLE",
            "next_action": "inspect_target_repository_and_build_tested_patch_manifest",
            "human_intervention_minimal": "none",
        }
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis})
        ledger.update({
            "updated_at": now,
            "execution_status": "submission_package_missing",
            "submission_blocked_stage": diagnosis["blocked_stage"],
            "next_action": diagnosis["next_action"],
        })
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis}))
        return 0

    candidate_id = str(package.get("candidate_id") or "")
    context = package.get("candidate_policy_context")
    if not isinstance(context, dict):
        return _policy_block(now, ledger, "submission_package_missing_policy_context", candidate_id)
    decision = evaluate_candidate(context, policy)
    if not decision.allowed:
        return _policy_block(now, ledger, decision.reason, candidate_id)
    if package.get("production_policy_mode") != policy.get("mode"):
        return _policy_block(now, ledger, "submission_package_policy_mode_stale", candidate_id)

    workspace = RESULTS / str(package.get("workspace") or "")
    manifest_relative = str(package.get("manifest_path") or "")
    manifest_path = RESULTS / manifest_relative
    try:
        receipt = submit_patch(manifest_path, workspace)
    except Exception as exc:
        diagnosis = diagnose_submission_failure(exc).to_dict()
        save_json(DIAGNOSIS_PATH, {"generated_at": now, **diagnosis})
        ledger.update({
            "updated_at": now,
            "execution_status": diagnosis["status"],
            "submission_blocked_stage": diagnosis["blocked_stage"],
            "submission_direct_cause": diagnosis["direct_cause"],
            "submission_root_cause": diagnosis["root_cause"],
            "next_action": diagnosis["next_action"],
        })
        save_json(LEDGER_PATH, ledger)
        print(json.dumps({"status": diagnosis["status"], "diagnosis": diagnosis}, ensure_ascii=False))
        return 0

    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    known = {item.get("pull_request_url") for item in receipts.get("receipts", [])}
    is_new_receipt = receipt["pull_request_url"] not in known
    if is_new_receipt:
        receipts.setdefault("receipts", []).append({**receipt, "production_policy_reason": decision.reason})
    receipts["updated_at"] = now
    save_json(RECEIPTS_PATH, receipts)
    ledger.update({
        "updated_at": now,
        "execution_status": "pull_request_submitted_verified" if receipt.get("verified") else "pull_request_submitted_unverified",
        "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)) + (1 if is_new_receipt else 0),
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)) + (1 if is_new_receipt else 0),
        "last_external_action_receipt": receipt["pull_request_url"],
        "last_submission_repository_mode": receipt["repository_mode"],
        "last_submission_policy_reason": decision.reason,
        "next_action": "monitor_pull_request_ci_reviews_and_maintainer_feedback",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "submitted", "receipt": receipt}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
