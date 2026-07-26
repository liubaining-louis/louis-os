#!/usr/bin/env python3
"""Promote a tested patch workspace into a submission package, or diagnose why not."""
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

RESULTS = ROOT / "results"
LEDGER_PATH = RESULTS / "monetization.json"
PACKAGE_PATH = RESULTS / "submission_package.json"
DIAGNOSIS_PATH = RESULTS / "submission_diagnosis.json"

DISCOVERY_BLOCKERS = {
    "no_genuine_narrow_payable_candidate",
    "no_safe_convertible_payable_candidate",
    "no_final_safe_convertible_payable_candidate",
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


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    ledger = load_json(LEDGER_PATH, {})
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
            "next_action": ledger.get("next_action") or "expand_verified_provider_sources_and_refresh",
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

    package = {
        "generated_at": now,
        "candidate_id": manifest["candidate_id"],
        "workspace": workspace.relative_to(RESULTS).as_posix(),
        "manifest_path": manifest_path.relative_to(RESULTS).as_posix(),
        "verified_patch_files": [{"path": item["path"], "sha256": item["sha256"]} for item in verified_files],
        "status": "ready_for_autonomous_submission",
    }
    save_json(PACKAGE_PATH, package)
    ledger.update({
        "updated_at": now,
        "execution_status": "ready_for_autonomous_submission",
        "submission_candidate_id": manifest["candidate_id"],
        "next_action": "submit_tested_patch_with_existing_github_identity",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "ready", "package": package}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
