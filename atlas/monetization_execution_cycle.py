"""Deterministic monetization execution with causal self-diagnosis.

This module binds an allow-listed internal command to a concrete executor. It
never performs an external submission, creates an account, accepts terms or
claims revenue. A cycle may only complete when repository files and a SHA-256
receipt prove that a deliverable was created.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .deliverable_executor import execute_candidate
from .monetization_root_cause import analyze_monetization
from .runner import ROOT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False) + "\n")


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _select_candidate(candidates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
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
            -float(item.get("execution_score", 0) or 0),
            -float(item.get("score", 0) or 0),
            str(item.get("id", "")),
        )
    )
    return eligible[0] if eligible else None


def _diagnosis(
    *,
    symptom: str,
    blocked_stage: str,
    direct_cause: str,
    root_cause: str,
    confidence: float,
    resolution_class: str,
    correction: str,
    validation_test: str,
    next_action: str,
    human_intervention_minimal: str = "none",
) -> dict[str, Any]:
    return {
        "symptom": symptom,
        "blocked_stage": blocked_stage,
        "direct_cause": direct_cause,
        "root_cause": root_cause,
        "confidence": confidence,
        "resolution_class": resolution_class,
        "correction": correction,
        "validation_test": validation_test,
        "next_action": next_action,
        "human_intervention_minimal": human_intervention_minimal,
    }


def _verify_receipt(receipt: Mapping[str, Any], root: Path) -> list[str]:
    artifact = Path(str(receipt["artifact_path"]))
    manifest = Path(str(receipt["manifest_path"]))
    workspace = Path(str(receipt["workspace"]))
    scope = workspace / "SCOPE.md"
    receipt_path = workspace / "execution_receipt.json"
    required = [artifact, manifest, scope, receipt_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"execution_evidence_missing:{','.join(missing)}")

    actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    expected_hash = str(receipt.get("artifact_sha256", ""))
    if not expected_hash or actual_hash != expected_hash:
        raise RuntimeError("artifact_sha256_mismatch")

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    stored_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if manifest_payload.get("artifact_sha256") != actual_hash:
        raise RuntimeError("manifest_sha256_mismatch")
    if stored_receipt.get("artifact_sha256") != actual_hash:
        raise RuntimeError("receipt_sha256_mismatch")
    if manifest_payload.get("externally_submitted") is not False:
        raise RuntimeError("unexpected_external_submission_state")

    return [_relative(path, root) for path in required]


def _persist_diagnosis(results: Path, diagnosis: Mapping[str, Any], root: Path) -> str:
    path = results / "monetization_execution_diagnosis.json"
    _write_json(path, {"generated_at": _now(), **dict(diagnosis)})
    return _relative(path, root)


def run_verified_deliverable_cycle(root: Path | None = None) -> dict[str, Any]:
    """Execute one internal deliverable cycle and return evidence or diagnosis."""
    repository_root = (root or ROOT).resolve()
    results = repository_root / "results"
    candidates_path = results / "monetization_candidates.json"
    ledger_path = results / "monetization.json"
    evidence_path = results / "evidence.jsonl"
    workspaces = results / "monetization_workspaces"
    now = _now()

    candidate_payload = _load_json(candidates_path, None)
    ledger = _load_json(ledger_path, {})
    if not isinstance(ledger, dict):
        ledger = {}

    if not isinstance(candidate_payload, dict) or not isinstance(candidate_payload.get("candidates"), list):
        diagnosis = _diagnosis(
            symptom="The requested execution cycle cannot load a valid candidate registry.",
            blocked_stage="candidate_loading",
            direct_cause="results/monetization_candidates.json is missing or invalid JSON.",
            root_cause="The runtime has no verified candidate state to pass to the deterministic executor.",
            confidence=1.0,
            resolution_class="AUTO_RESOLVABLE",
            correction="Run the authenticated opportunity scout, persist a valid candidate registry, then retry the same command.",
            validation_test="monetization_candidates.json exists, parses and contains a candidates array",
            next_action="regenerate_verified_candidates",
        )
        diagnosis_evidence = _persist_diagnosis(results, diagnosis, repository_root)
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "blocked",
                "execution_blocked_reason": "candidate_file_unavailable",
                "root_cause_code": "candidate_file_unavailable",
                "next_action": diagnosis["correction"],
            }
        )
        _write_json(ledger_path, ledger)
        return {
            "status": "blocked",
            "execution_mode": "deterministic_internal_executor",
            "reason": "candidate_file_unavailable",
            "diagnosis": diagnosis,
            "evidence": [diagnosis_evidence, _relative(ledger_path, repository_root)],
            "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
            "external_actions_submitted": int(ledger.get("external_actions_submitted", 0) or 0),
        }

    candidates = list(candidate_payload.get("candidates") or [])
    selected = _select_candidate(candidates)
    if selected is None:
        causal = analyze_monetization(ledger=ledger, candidates=candidates).to_dict()
        primary = causal["primary_cause"]
        executable_unverified = sum(
            item.get("readiness_status") == "executable_now"
            and item.get("external_prerequisites_cleared") is True
            and item.get("authenticity_verified") is not True
            for item in candidates
        )
        if executable_unverified:
            direct_cause = (
                f"{executable_unverified} candidate(s) look executable but lack current authenticity proof."
            )
            root_cause = (
                "The candidate registry predates or bypassed the authenticity validator, so execution fails closed."
            )
            correction = (
                "Refresh candidates through the current scout and authenticity validator before creating a deliverable."
            )
            reason = "no_authentic_executable_candidate"
            success_test = "at least one candidate has authenticity_verified=true and authenticity_status=verified"
        else:
            direct_cause = primary["explanation"]
            root_cause = "The first broken stage in the monetization funnel has not yet produced an executable candidate."
            correction = primary["corrective_action"]
            reason = primary["code"]
            success_test = primary["success_metric"]
        diagnosis = _diagnosis(
            symptom="Revenue remains at 0 € and no internal deliverable can be started.",
            blocked_stage="candidate_selection",
            direct_cause=direct_cause,
            root_cause=root_cause,
            confidence=float(primary.get("confidence", 0.95)),
            resolution_class="AUTO_RESOLVABLE",
            correction=correction,
            validation_test=success_test,
            next_action="refresh_and_revalidate_candidates",
        )
        diagnosis_evidence = _persist_diagnosis(results, diagnosis, repository_root)
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "blocked",
                "execution_blocked_reason": reason,
                "root_cause_code": reason,
                "root_cause_confidence": diagnosis["confidence"],
                "primary_blocker": diagnosis["root_cause"],
                "corrective_action": diagnosis["correction"],
                "root_cause_success_metric": diagnosis["validation_test"],
                "next_action": diagnosis["correction"],
            }
        )
        _write_json(ledger_path, ledger)
        _append_jsonl(
            evidence_path,
            {
                "timestamp": now,
                "kind": "execution_blocked_with_causal_diagnosis",
                "reason": reason,
                "source": diagnosis_evidence,
                "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
            },
        )
        return {
            "status": "blocked",
            "execution_mode": "deterministic_internal_executor",
            "reason": reason,
            "diagnosis": diagnosis,
            "evidence": [
                diagnosis_evidence,
                _relative(candidates_path, repository_root),
                _relative(ledger_path, repository_root),
            ],
            "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
            "external_actions_submitted": int(ledger.get("external_actions_submitted", 0) or 0),
        }

    try:
        receipt = asdict(execute_candidate(dict(selected), workspaces))
        evidence = _verify_receipt(receipt, repository_root)
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "deliverable_created",
                "current_execution_candidate": receipt["candidate_id"],
                "current_execution_workspace": receipt["workspace"],
                "current_execution_artifact": receipt["artifact_path"],
                "current_execution_artifact_sha256": receipt["artifact_sha256"],
                "internal_execution_actions": int(ledger.get("internal_execution_actions", 0) or 0) + 1,
                "external_actions_submitted": int(ledger.get("external_actions_submitted", 0) or 0),
                "internet_actions_submitted": int(ledger.get("internet_actions_submitted", 0) or 0),
                "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
                "next_action": "Validate the artifact against the authoritative acceptance criteria, then prepare a submission package.",
            }
        )
        _write_json(ledger_path, ledger)
        evidence.append(_relative(ledger_path, repository_root))
        _append_jsonl(
            evidence_path,
            {
                "timestamp": now,
                "kind": "internal_deliverable_created",
                **receipt,
                "verified_evidence": evidence,
            },
        )
        return {
            "status": "completed",
            "execution_mode": "deterministic_internal_executor",
            "result": "A concrete internal deliverable and verified SHA-256 receipt were created.",
            "receipt": receipt,
            "evidence": evidence,
            "diagnosis": _diagnosis(
                symptom="The prior command path returned prose instead of executing.",
                blocked_stage="command_dispatch",
                direct_cause="The command is now bound to a deterministic internal executor.",
                root_cause="The generic LLM mission route was not an execution engine.",
                confidence=1.0,
                resolution_class="AUTO_RESOLVED",
                correction="Use the deterministic executor and require evidence before completion.",
                validation_test="workspace files exist and artifact SHA-256 matches manifest and receipt",
                next_action=ledger["next_action"],
            ),
            "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
            "external_actions_submitted": int(ledger.get("external_actions_submitted", 0) or 0),
        }
    except Exception as exc:
        diagnosis = _diagnosis(
            symptom="The deterministic deliverable execution failed.",
            blocked_stage="deliverable_execution_or_verification",
            direct_cause=f"{type(exc).__name__}: {exc}",
            root_cause="The concrete executor or its evidence contract encountered an unhandled technical defect.",
            confidence=0.99,
            resolution_class="AUTO_RESOLVABLE",
            correction="Reproduce the exception, add a regression test, correct the executor and retry the same candidate.",
            validation_test="the regression test and full CI pass, then the cycle returns completed with non-empty evidence",
            next_action="open_targeted_regression_fix",
        )
        diagnosis_evidence = _persist_diagnosis(results, diagnosis, repository_root)
        ledger.update(
            {
                "updated_at": now,
                "execution_status": "failed",
                "execution_blocked_reason": f"{type(exc).__name__}:{exc}",
                "root_cause_code": "technical_execution_failure",
                "primary_blocker": diagnosis["root_cause"],
                "corrective_action": diagnosis["correction"],
                "next_action": diagnosis["correction"],
            }
        )
        _write_json(ledger_path, ledger)
        return {
            "status": "failed",
            "execution_mode": "deterministic_internal_executor",
            "error": f"{type(exc).__name__}: {exc}",
            "diagnosis": diagnosis,
            "evidence": [diagnosis_evidence, _relative(ledger_path, repository_root)],
            "revenue_confirmed_eur": float(ledger.get("revenue_confirmed_eur", 0.0) or 0.0),
            "external_actions_submitted": int(ledger.get("external_actions_submitted", 0) or 0),
        }
