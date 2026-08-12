"""Strict 5–50 USDC cash-first execution wrapper.

This lane fails closed: candidates outside the economic window are never executed,
and a generic scaffold can never be reported as a completed deliverable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .monetization_execution_cycle import run_verified_deliverable_cycle
from .runner import ROOT

MIN_USDC = 5.0
MAX_USDC = 50.0


def _reward_is_verified(candidate: Mapping[str, Any]) -> bool:
    if any(
        candidate.get(key) is True
        for key in (
            "reward_verified",
            "authenticity_verified",
            "opportunity_authenticity_verified",
        )
    ):
        return True
    statuses = {
        str(candidate.get("authenticity_status") or "").casefold(),
        str(candidate.get("opportunity_authenticity_status") or "").casefold(),
    }
    return bool(
        statuses
        & {
            "verified",
            "verified_authoritative_reward",
            "verified_platform_backed_reward",
        }
    )


def _as_finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if math.isfinite(amount) else None


def _amount(candidate: Mapping[str, Any]) -> float | None:
    if not _reward_is_verified(candidate):
        return None
    for key in ("reward_usdc", "budget_usdc", "amount_usdc", "normalized_reward_usdc"):
        if key in candidate:
            return _as_finite_float(candidate.get(key))
    currency = str(candidate.get("currency") or candidate.get("reward_currency") or "").strip().upper()
    if currency == "USDC":
        for key in ("reward", "budget", "amount", "reward_amount", "reward_hint"):
            if key in candidate:
                return _as_finite_float(candidate.get(key))
    return None


def _generic_scaffold(text: str) -> bool:
    lowered = text.casefold()
    markers = (
        "draft solution scaffold",
        "# draft deliverable",
        "reviewable internal draft",
        "intended for iterative refinement",
        "ready for opportunity-specific refinement",
        "replace every assumption with source-backed requirements",
        "status': 'draft'",
        '"status": "draft"',
    )
    return any(marker in lowered for marker in markers)


def run_cash_first_usdc_cycle(root: Path | None = None) -> dict[str, Any]:
    repository_root = (root or ROOT).resolve()
    candidates_path = repository_root / "results" / "monetization_candidates.json"
    try:
        payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return run_verified_deliverable_cycle(repository_root)

    original = list(payload["candidates"])
    in_window = []
    rejected = []
    for candidate in original:
        amount = _amount(candidate) if isinstance(candidate, dict) else None
        if amount is not None and MIN_USDC <= amount <= MAX_USDC:
            enriched = dict(candidate)
            enriched["cash_first_reward_usdc"] = amount
            in_window.append(enriched)
        else:
            rejected.append(
                {
                    "id": candidate.get("id") if isinstance(candidate, dict) else None,
                    "reward_usdc": amount,
                    "reason": "outside_5_50_usdc_or_unverified_amount",
                }
            )

    if not in_window:
        return {
            "status": "blocked",
            "execution_mode": "deterministic_cash_first_usdc_discovery_executor",
            "reason": "no_candidate_in_5_50_usdc_window",
            "diagnosis": {
                "symptom": "No candidate passes the mandatory 5–50 USDC economic gate.",
                "blocked_stage": "economic_candidate_gate",
                "direct_cause": "All current candidates are below 5 USDC, above 50 USDC, or lack a verified USDC amount.",
                "root_cause": "Candidate discovery did not produce an economically eligible micro-mission.",
                "confidence": 1.0,
                "resolution_class": "AUTO_RESOLVABLE",
                "correction": "Refresh sources until a live candidate with verified reward between 5 and 50 USDC exists.",
                "validation_test": "at least one executable candidate has a verified 5 <= reward_usdc <= 50",
                "next_action": "refresh_5_50_usdc_candidates",
                "human_intervention_minimal": "none",
            },
            "evidence": ["results/monetization_candidates.json"],
            "economic_gate": {"min_usdc": MIN_USDC, "max_usdc": MAX_USDC, "eligible": 0, "rejected": rejected},
            "revenue_confirmed_eur": 0.0,
            "external_actions_submitted": 0,
        }

    # Temporarily expose only economically eligible candidates to the existing deterministic executor.
    candidates_path.write_text(json.dumps({**payload, "candidates": in_window}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        outcome = dict(run_verified_deliverable_cycle(repository_root))
    finally:
        candidates_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outcome["economic_gate"] = {"min_usdc": MIN_USDC, "max_usdc": MAX_USDC, "eligible": len(in_window), "rejected": rejected}
    if outcome.get("status") == "completed":
        receipt = outcome.get("receipt") or {}
        artifact = Path(str(receipt.get("artifact_path") or ""))
        try:
            content = artifact.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""
        if not content.strip() or _generic_scaffold(content):
            outcome["status"] = "blocked"
            outcome["reason"] = "deliverable_not_acceptance_ready"
            outcome["result"] = "Candidate passed the economic gate, but the generated artifact is only a generic draft and cannot count as completed."
            outcome["diagnosis"] = {
                "symptom": "A generic scaffold was generated for a real paid mission.",
                "blocked_stage": "deliverable_quality_gate",
                "direct_cause": "The artifact is not demonstrably tailored to authoritative acceptance criteria.",
                "root_cause": "The generic executor produced a placeholder rather than an opportunity-specific solution.",
                "confidence": 1.0,
                "resolution_class": "AUTO_RESOLVABLE",
                "correction": "Fetch authoritative acceptance criteria, implement the requested solution, run its specified validation/benchmark, and only then mark completed.",
                "validation_test": "artifact is opportunity-specific, contains no draft/scaffold markers, and has passing acceptance-test evidence",
                "next_action": "build_acceptance_specific_solution",
                "human_intervention_minimal": "none",
            }
    return outcome
