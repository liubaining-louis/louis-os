#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from atlas.multi_model_monetization import candidate_fingerprint, run_team_review
from atlas.runner import ROOT

RESULTS = ROOT / "results"
CANDIDATES = RESULTS / "monetization_candidates.json"
LEDGER = RESULTS / "monetization.json"
OUT = RESULTS / "multi_model_monetization.json"


def load_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> int:
    payload = load_json(CANDIDATES, {})
    candidates = payload.get("candidates") if isinstance(payload, dict) else []
    if not isinstance(candidates, list):
        candidates = []
    ledger = load_json(LEDGER, {})
    if not isinstance(ledger, dict):
        ledger = {}
    previous = load_json(OUT, {})
    artifact_sha = str(ledger.get("current_execution_artifact_sha256") or "") or None
    fingerprint = candidate_fingerprint(candidates[:5], artifact_sha)
    if isinstance(previous, dict) and previous.get("fingerprint") == fingerprint:
        print(json.dumps({"status": "cached", "fingerprint": fingerprint}))
        return 0

    artifact_text = None
    artifact_path = ledger.get("current_execution_artifact")
    if artifact_path:
        try:
            artifact_text = Path(str(artifact_path)).read_text(encoding="utf-8")[:20000]
        except OSError:
            artifact_text = None

    try:
        result = run_team_review(candidates, artifact_text=artifact_text, artifact_sha256=artifact_sha)
        output = {"updated_at": datetime.now(timezone.utc).isoformat(), **asdict(result)}
    except Exception as exc:
        output = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": fingerprint,
            "status": "failed",
            "critic_pass": False,
            "recommendation": "reject",
            "revision_required": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    save_json(OUT, output)

    ledger.update({
        "multi_model_review_status": output.get("status"),
        "multi_model_selected_candidate": output.get("selected_candidate_id"),
        "multi_model_recommendation": output.get("recommendation", "reject"),
        "multi_model_critic_pass": bool(output.get("critic_pass") is True),
        "multi_model_review_fingerprint": output.get("fingerprint"),
    })
    if output.get("critic_pass") is not True:
        ledger["submission_ai_gate"] = "blocked_pending_critic_pass"
    else:
        ledger["submission_ai_gate"] = "critic_passed_non_authoritative"
    save_json(LEDGER, ledger)
    print(json.dumps({
        "status": output.get("status"),
        "recommendation": output.get("recommendation"),
        "critic_pass": output.get("critic_pass"),
        "selected_candidate_id": output.get("selected_candidate_id"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
