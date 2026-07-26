#!/usr/bin/env python3
"""Run one evidence-backed universal internet market cycle."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.universal_market import (
    CapabilityRegistry,
    InternetOpportunity,
    SourceState,
    UniversalMarketEngine,
)
from atlas.usagov_challenge_source import USAGovChallengeSource

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
CAPABILITIES_PATH = ROOT / "config" / "universal_capabilities.json"
SOURCES_PATH = ROOT / "config" / "universal_market_sources.json"
PROMPT_PATH = ROOT / "docs" / "prompts" / "UNIVERSAL_MARKET_MONETIZATION.md"
OPPORTUNITIES_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
LEDGER_PATH = RESULTS / "monetization.json"
GITHUB_CANDIDATES_PATH = RESULTS / "monetization_candidates.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def normalize_github_candidates() -> tuple[list[InternetOpportunity], SourceState]:
    payload = load_json(GITHUB_CANDIDATES_PATH, {})
    candidates = payload.get("candidates") if isinstance(payload, Mapping) else []
    candidates = candidates if isinstance(candidates, list) else []
    opportunities: list[InternetOpportunity] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("canonical_issue_url") or item.get("url") or "")
        reward = float(item.get("reward_amount") or item.get("reward_hint") or 0.0)
        verified = bool(
            item.get("opportunity_authenticity_verified")
            or item.get("authenticity_verified")
            or item.get("credible_payable")
        )
        evidence_raw = item.get("opportunity_authenticity_evidence") or item.get("authenticity_evidence") or []
        evidence = tuple(str(value) for value in evidence_raw if str(value).strip())
        capability = str(item.get("patch_handler") or "").strip()
        if not capability and isinstance(item.get("capability_match"), Mapping):
            capability = str(item["capability_match"].get("capability_id") or "")
        if not capability:
            capability = "technical_proposal"
        existing_identity = item.get("submission_capability") == "existing_authorized_github_identity"
        body = str(item.get("body") or item.get("title") or "")
        if not url or not str(item.get("title") or "").strip():
            continue
        opportunities.append(
            InternetOpportunity(
                source_id="github_bounties",
                source_category="code_bounty",
                source_url=url,
                title=str(item.get("title") or ""),
                description=body[:4000],
                reward_amount=reward,
                currency=str(item.get("currency") or "USD"),
                reward_verified=verified,
                payment_evidence=evidence if verified and reward > 0 else (),
                required_capabilities=(capability,),
                observed_at=str(item.get("updated_at") or payload.get("generated_at") or "1970-01-01T00:00:00+00:00"),
                account_required=not existing_identity,
                terms_required=False,
                legal_entity_required=False,
                identity_or_kyc_required=False,
                security_scope_authorized=True,
                accessibility=0.95,
                human_dependency=0.10,
                risk=0.20,
                cost=0.05,
                competition=min(1.0, float(item.get("competition_score") or item.get("active_attempts") or 0) / 10.0),
                time_to_cash_days=30,
                evidence=tuple(dict.fromkeys((url,) + evidence)),
                metadata={"original_candidate_id": item.get("id"), "source_payload": "monetization_candidates.json"},
            )
        )
    status = "ok" if opportunities else "empty"
    root_cause = str(payload.get("root_cause_code") or "") if isinstance(payload, Mapping) else ""
    return opportunities, SourceState(
        source_id="github_bounties",
        category="code_bounty",
        status=status,
        reason=root_cause,
        evidence=(str(GITHUB_CANDIDATES_PATH.relative_to(ROOT)),),
        observed_count=len(opportunities),
    )


def catalog_source_states(existing_ids: set[str]) -> list[SourceState]:
    catalog = load_json(SOURCES_PATH, {"sources": []})
    states: list[SourceState] = []
    for item in catalog.get("sources", []):
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("id") or "")
        if not source_id or source_id in existing_ids:
            continue
        category = str(item.get("category") or "unknown")
        discovery = str(item.get("discovery_status") or "disabled")
        credential_env = str(item.get("credential_env") or "")
        credential_present = bool(credential_env and os.getenv(credential_env))
        if discovery == "credential_gated":
            status = "credential_available_adapter_pending" if credential_present else "credential_gated"
            reason = (
                f"{credential_env} is present; source-specific adapter can be activated after tests."
                if credential_present
                else f"Credential {credential_env} and account authorization are required."
            )
        elif discovery == "enabled_when_configured":
            status = "awaiting_reviewed_configuration"
            reason = "No reviewed partner feed endpoint is configured."
        else:
            status = discovery
            reason = str(item.get("notes") or "")
        states.append(
            SourceState(
                source_id=source_id,
                category=category,
                status=status,
                reason=reason,
                evidence=(str(item.get("official_url") or ""),),
                observed_count=0,
            )
        )
    return states


def capability_issue_payload(gap: Mapping[str, Any]) -> dict[str, str]:
    capability_id = str(gap["capability_id"])
    specification = gap.get("specification") or {}
    marker = str(gap.get("marker") or f"<!-- louis-capability-gap:{capability_id} -->")
    title = f"Capability gap: {capability_id}"
    body = "\n".join(
        [
            marker,
            "## Market-backed objective",
            str(specification.get("objective") or ""),
            "",
            f"- Priority score: {gap.get('priority_score')}",
            f"- Referenced market value: {gap.get('market_value')}",
            f"- Originating opportunity IDs: {', '.join(gap.get('originating_opportunity_ids') or [])}",
            f"- Market evidence: {specification.get('originating_market_url')}",
            "",
            "## Required interface",
            "```json",
            json.dumps(specification.get("required_interface") or {}, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Acceptance tests",
            *[f"- [ ] {item}" for item in specification.get("acceptance_tests") or []],
            "",
            "## Promotion and budget",
            f"- {specification.get('promotion_rule')}",
            f"- {specification.get('budget_rule')}",
            "",
            "## Mandatory continuation",
            str(specification.get("retry_action") or "Re-run universal market qualification after promotion."),
            "",
            "No external submission, account creation, legal acceptance or revenue claim is authorized by this internal issue.",
        ]
    )
    return {"title": title, "body": body, "marker": marker}


def main() -> int:
    capabilities = CapabilityRegistry.from_file(CAPABILITIES_PATH)
    all_opportunities: list[InternetOpportunity] = []
    states: list[SourceState] = []

    github_opportunities, github_state = normalize_github_candidates()
    all_opportunities.extend(github_opportunities)
    states.append(github_state)

    usagov_opportunities, usagov_state = USAGovChallengeSource().collect()
    all_opportunities.extend(usagov_opportunities)
    states.append(usagov_state)

    states.extend(catalog_source_states({state.source_id for state in states}))
    evaluation = UniversalMarketEngine(capabilities).evaluate(all_opportunities, states)
    payload = evaluation.to_dict()
    payload["mission_prompt"] = str(PROMPT_PATH.relative_to(ROOT))
    payload["mission_prompt_sha256"] = prompt_sha256()
    save_json(OPPORTUNITIES_PATH, payload)

    issue_payloads = [capability_issue_payload(item) for item in payload["capability_gaps"]]
    backlog = {
        "schema_version": "1.0",
        "generated_at": payload["generated_at"],
        "count": len(issue_payloads),
        "items": [
            {**gap, "issue": issue}
            for gap, issue in zip(payload["capability_gaps"], issue_payloads, strict=True)
        ],
    }
    save_json(BACKLOG_PATH, backlog)

    decision_counts = payload["decision_counts"]
    cycle = {
        "schema_version": "1.0",
        "generated_at": payload["generated_at"],
        "mission_prompt_sha256": payload["mission_prompt_sha256"],
        "sources_total": len(states),
        "sources_ok_or_partial": sum(state.status in {"ok", "partial"} for state in states),
        "sources_credential_gated": sum("credential" in state.status for state in states),
        "opportunities_observed": len(payload["opportunities"]),
        "opportunities_executable_now": decision_counts["executable_now"],
        "opportunities_prepare_then_gate": decision_counts["prepare_then_gate"],
        "opportunities_capability_build": decision_counts["capability_build"],
        "opportunities_rejected": decision_counts["rejected"],
        "capability_gaps_created": len(payload["capability_gaps"]),
        "external_submissions_verified": 0,
        "revenue_verified_eur": float(load_json(LEDGER_PATH, {}).get("revenue_confirmed_eur", 0.0) or 0.0),
        "next_action": (
            "route_executable_opportunities_to_verified_executor"
            if decision_counts["executable_now"]
            else "build_highest_priority_market_backed_capability"
            if payload["capability_gaps"]
            else "activate_next_authorized_official_source"
        ),
        "evidence": [
            str(OPPORTUNITIES_PATH.relative_to(ROOT)),
            str(BACKLOG_PATH.relative_to(ROOT)),
            str(SOURCES_PATH.relative_to(ROOT)),
            str(CAPABILITIES_PATH.relative_to(ROOT)),
        ],
    }
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    ledger.update(
        {
            "updated_at": payload["generated_at"],
            "universal_market_engine": "active",
            "universal_market_sources_total": cycle["sources_total"],
            "universal_market_opportunities_observed": cycle["opportunities_observed"],
            "universal_market_executable_now": cycle["opportunities_executable_now"],
            "universal_market_prepare_then_gate": cycle["opportunities_prepare_then_gate"],
            "universal_market_capability_build": cycle["opportunities_capability_build"],
            "market_backed_capability_gaps": cycle["capability_gaps_created"],
            "next_action": cycle["next_action"],
        }
    )
    save_json(LEDGER_PATH, ledger)
    print(json.dumps(cycle, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
