#!/usr/bin/env python3
"""Prepare concrete proposal dossiers for simple marketplace missions.

This step performs all reversible preparation before asking for an account or terms
acceptance. It never submits a bid and never records revenue.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
DOSSIERS_ROOT = RESULTS / "simple_mission_dossiers"
RECEIPT_PATH = RESULTS / "simple_mission_dossier_receipts.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:80] or "mission"


def build_proposal(opportunity: Mapping[str, Any]) -> str:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    effort = float(metadata.get("estimated_effort_hours") or 8.0)
    budget_min = float(metadata.get("budget_min") or opportunity.get("reward_amount") or 0.0)
    currency = str(opportunity.get("currency") or "")
    title = str(opportunity.get("title") or "")
    source = str(opportunity.get("source_url") or "")
    description = str(opportunity.get("description") or "")[:1_800]
    capability = ", ".join(str(item) for item in opportunity.get("required_capabilities") or [])
    platform = str(metadata.get("platform") or opportunity.get("source_id") or "marketplace")
    budget_kind = str(metadata.get("budget_kind") or "fixed")
    quality_checks = _quality_checks(capability)
    client_message = "\n".join(
        [
            "Hello,",
            "",
            f"I can deliver the requested work through {platform} within approximately {effort:g} hours after receiving the complete source material and acceptance criteria.",
            f"My conservative quote basis is {budget_min:g} {currency} ({budget_kind}).",
            "",
            "My delivery approach:",
            "1. confirm the exact input fields, source files and expected output format;",
            "2. produce the requested dataset, research dossier or document in a reviewable format;",
            "3. run completeness, formatting and consistency checks;",
            "4. deliver the final artifact together with a short validation note.",
            "",
            "Before starting, please confirm that all required source material can be shared through the platform and that the public description contains the complete scope.",
            "",
            "Regards",
        ]
    )
    return "\n".join(
        [
            f"# Prepared proposal dossier — {title}",
            "",
            f"Platform: {platform}",
            f"Source: {source}",
            f"Capability: {capability}",
            f"Conservative proposed quote: {budget_min:g} {currency}",
            f"Budget basis: {budget_kind}",
            f"Estimated effort: {effort:g} hours",
            "External submission: false",
            "",
            "## Public scope excerpt",
            description,
            "",
            "## Client-facing proposal",
            client_message,
            "",
            "## Deliverable validation",
            *[f"- {item}" for item in quality_checks],
            "",
            "## Pre-submission checks",
            "- confirm the project remains open and the public budget is unchanged;",
            "- confirm the quote count and deadline still satisfy the cash-first policy;",
            "- confirm no false credential, identity, experience or portfolio claim is added;",
            "- use only the authorized account holder identity;",
            "- accept platform terms only after user review;",
            "- require the platform payment-protection mechanism before work begins where available;",
            "- do not configure payout or complete KYC until the platform actually requires it;",
            "- preserve the platform submission receipt if a proposal or quote is sent.",
            "",
        ]
    )


def _quality_checks(capability: str) -> tuple[str, ...]:
    checks = [
        "verify every requested field is present or explicitly marked unavailable;",
        "deduplicate records and preserve source URLs or source-file references;",
        "run deterministic formatting and consistency checks before delivery;",
    ]
    if "evidence_research_dossier" in capability:
        checks.append("use public authoritative sources and include an evidence column for each record;")
    if "python_data_analysis" in capability:
        checks.append("validate row counts, formulas, types and output schema with a reproducible script;")
    if "translation_delivery" in capability:
        checks.append("preserve meaning, terminology, names, numbers and requested target-language register;")
    if "structured_document_delivery" in capability:
        checks.append("check spelling, structure, pagination and requested output format;")
    return tuple(checks)


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, dict) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    # Rebuild from the current qualified market only. A rejected or expired mission
    # must not leave behind an apparently actionable proposal artifact.
    if DOSSIERS_ROOT.exists():
        shutil.rmtree(DOSSIERS_ROOT)
    DOSSIERS_ROOT.mkdir(parents=True, exist_ok=True)

    receipts: list[dict[str, Any]] = []
    prepared = 0
    for opportunity in market["opportunities"]:
        if not isinstance(opportunity, dict):
            continue
        decision = opportunity.get("decision") if isinstance(opportunity.get("decision"), Mapping) else {}
        metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
        if metadata.get("source_kind") != "public_freelance_listing":
            continue
        if decision.get("status") != "prepare_then_gate":
            continue
        if not metadata.get("submission_dossier_required"):
            continue

        opportunity_id = str(opportunity.get("opportunity_id") or "")
        platform = str(metadata.get("platform") or opportunity.get("source_id") or "marketplace")
        workspace = DOSSIERS_ROOT / safe_slug(opportunity_id)
        workspace.mkdir(parents=True, exist_ok=True)
        proposal_path = workspace / "proposal.md"
        proposal_path.write_text(build_proposal(opportunity), encoding="utf-8")
        proposal_hash = sha256(proposal_path)
        manifest_path = workspace / "manifest.json"
        manifest = {
            "schema_version": "1.1",
            "opportunity_id": opportunity_id,
            "source_id": opportunity.get("source_id"),
            "platform": platform,
            "source_url": opportunity.get("source_url"),
            "title": opportunity.get("title"),
            "reward_amount": opportunity.get("reward_amount"),
            "currency": opportunity.get("currency"),
            "deadline": opportunity.get("deadline"),
            "proposal_path": str(proposal_path.relative_to(ROOT)),
            "proposal_sha256": proposal_hash,
            "externally_submitted": False,
            "external_receipt": None,
            "revenue_verified": False,
        }
        save_json(manifest_path, manifest)

        metadata = dict(metadata)
        metadata.update(
            {
                "submission_dossier_prepared": True,
                "proposal_path": str(proposal_path.relative_to(ROOT)),
                "proposal_sha256": proposal_hash,
                "proposal_manifest_path": str(manifest_path.relative_to(ROOT)),
                "human_action_instructions": [
                    f"Authorize use of a truthful {platform} account and review/accept the platform terms so Louis OS can submit the already prepared proposal or quote. Do not complete KYC or configure payout unless the platform explicitly requests it later."
                ],
            }
        )
        opportunity["metadata"] = metadata
        evidence = [
            str(item)
            for item in opportunity.get("evidence") or []
            if not str(item).startswith("results/simple_mission_dossiers/")
        ]
        for path in (proposal_path, manifest_path):
            relative = str(path.relative_to(ROOT))
            if relative not in evidence:
                evidence.append(relative)
        opportunity["evidence"] = evidence
        receipts.append(manifest)
        prepared += 1

    save_json(MARKET_PATH, market)
    save_json(
        RECEIPT_PATH,
        {
            "schema_version": "1.1",
            "generated_at": market.get("generated_at"),
            "prepared_count": prepared,
            "platforms": sorted({str(item.get("platform") or "") for item in receipts if item.get("platform")}),
            "receipts": receipts,
            "external_submissions_verified": 0,
            "revenue_verified_eur": 0.0,
        },
    )

    cycle = load_json(CYCLE_PATH, {})
    cycle["simple_mission_dossiers_prepared"] = prepared
    cycle["next_action"] = (
        "prioritize_prepared_simple_missions_and_request_minimal_account_gate"
        if prepared
        else cycle.get("next_action") or "activate_next_small_mission_source"
    )
    evidence = list(cycle.get("evidence") or [])
    relative = str(RECEIPT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)
    print(json.dumps({"prepared": prepared, "submitted": 0, "revenue_eur": 0.0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
