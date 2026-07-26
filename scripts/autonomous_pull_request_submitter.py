#!/usr/bin/env python3
"""Submit one tested repository patch and persist an auditable receipt."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.autonomous_submission import diagnose_submission_failure, submit_patch

RESULTS = ROOT / "results"
PACKAGE_PATH = RESULTS / "submission_package.json"
RECEIPTS_PATH = RESULTS / "submission_receipts.json"
DIAGNOSIS_PATH = RESULTS / "submission_diagnosis.json"
LEDGER_PATH = RESULTS / "monetization.json"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    package = load_json(PACKAGE_PATH, None)
    ledger = load_json(LEDGER_PATH, {})
    if not isinstance(package, dict):
        diagnosis = {
            "status": "blocked",
            "blocked_stage": "submission_package_loading",
            "direct_cause": "results/submission_package.json is missing or invalid.",
            "root_cause": "No tested repository patch has been packaged for submission.",
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
        print(json.dumps({"status": "blocked", "diagnosis": diagnosis, "evidence": [str(DIAGNOSIS_PATH.relative_to(ROOT)), str(LEDGER_PATH.relative_to(ROOT))]}))
        return 0

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
        print(json.dumps({"status": diagnosis["status"], "diagnosis": diagnosis, "evidence": [str(DIAGNOSIS_PATH.relative_to(ROOT)), str(LEDGER_PATH.relative_to(ROOT))]}, ensure_ascii=False))
        return 0

    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    known = {item.get("pull_request_url") for item in receipts.get("receipts", [])}
    if receipt["pull_request_url"] not in known:
        receipts.setdefault("receipts", []).append(receipt)
    receipts["updated_at"] = now
    save_json(RECEIPTS_PATH, receipts)
    ledger.update({
        "updated_at": now,
        "execution_status": "pull_request_submitted_verified" if receipt.get("verified") else "pull_request_submitted_unverified",
        "external_actions_submitted": int(ledger.get("external_actions_submitted", 0)) + 1,
        "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0)) + 1,
        "last_external_action_receipt": receipt["pull_request_url"],
        "last_submission_repository_mode": receipt["repository_mode"],
        "next_action": "monitor_pull_request_ci_reviews_and_maintainer_feedback",
    })
    save_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "submitted", "receipt": receipt, "evidence": [str(RECEIPTS_PATH.relative_to(ROOT)), str(LEDGER_PATH.relative_to(ROOT))]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
