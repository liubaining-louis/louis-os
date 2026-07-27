#!/usr/bin/env python3
"""Refresh official simple-mission sources and merge them into market evidence."""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.guru_simple_mission_source import GuruPublicJobsSource
from atlas.simple_mission_sources import FreelancerPublicJobsSource
from atlas.truelancer_simple_mission_source import TruelancerPublicJobsSource
from atlas.universal_market import CapabilityRegistry, InternetOpportunity, SourceState, UniversalMarketEngine

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
RECEIPT_PATH = RESULTS / "simple_mission_source_refresh.json"
CAPABILITIES_PATH = ROOT / "config" / "universal_capabilities.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def opportunity_from_dict(item: Mapping[str, Any]) -> InternetOpportunity:
    names = {field.name for field in fields(InternetOpportunity)}
    payload = {name: item.get(name) for name in names}
    for name in ("payment_evidence", "required_capabilities", "evidence"):
        payload[name] = tuple(payload.get(name) or [])
    payload["metadata"] = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    return InternetOpportunity(**payload)


def source_state_from_dict(item: Mapping[str, Any]) -> SourceState:
    return SourceState(
        source_id=str(item.get("source_id") or ""),
        category=str(item.get("category") or ""),
        status=str(item.get("status") or ""),
        reason=str(item.get("reason") or ""),
        evidence=tuple(str(value) for value in item.get("evidence") or []),
        observed_count=int(item.get("observed_count") or 0),
    )


def capability_issue_payload(gap: Mapping[str, Any]) -> dict[str, str]:
    capability_id = str(gap["capability_id"])
    specification = gap.get("specification") or {}
    marker = str(gap.get("marker") or f"<!-- louis-capability-gap:{capability_id} -->")
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
            *[f"- [ ] {value}" for value in specification.get("acceptance_tests") or []],
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
    return {"title": f"Capability gap: {capability_id}", "body": body, "marker": marker}


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, Mapping) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    opportunities = [opportunity_from_dict(item) for item in market.get("opportunities", []) if isinstance(item, Mapping)]
    existing_states = [
        source_state_from_dict(item) for item in market.get("source_states", []) if isinstance(item, Mapping)
    ]
    source_results = [
        FreelancerPublicJobsSource().collect(),
        GuruPublicJobsSource().collect(),
        TruelancerPublicJobsSource().collect(),
    ]

    refreshed_ids = {state.source_id for _, state in source_results}
    states = [state for state in existing_states if state.source_id not in refreshed_ids]
    for rows, state in source_results:
        opportunities.extend(rows)
        states.append(state)

    evaluation = UniversalMarketEngine(CapabilityRegistry.from_file(CAPABILITIES_PATH)).evaluate(opportunities, states)
    payload = evaluation.to_dict()
    payload["mission_prompt"] = market.get("mission_prompt")
    payload["mission_prompt_sha256"] = market.get("mission_prompt_sha256")
    save_json(MARKET_PATH, payload)

    issue_payloads = [capability_issue_payload(item) for item in payload["capability_gaps"]]
    save_json(
        BACKLOG_PATH,
        {
            "schema_version": "1.0",
            "generated_at": payload["generated_at"],
            "count": len(issue_payloads),
            "items": [
                {**gap, "issue": issue}
                for gap, issue in zip(payload["capability_gaps"], issue_payloads, strict=True)
            ],
        },
    )

    decision_counts = payload["decision_counts"]
    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "generated_at": payload["generated_at"],
            "sources_total": len(states),
            "sources_ok_or_partial": sum(state.status in {"ok", "partial"} for state in states),
            "sources_credential_gated": sum("credential" in state.status for state in states),
            "opportunities_observed": len(payload["opportunities"]),
            "opportunities_executable_now": decision_counts["executable_now"],
            "opportunities_prepare_then_gate": decision_counts["prepare_then_gate"],
            "opportunities_capability_build": decision_counts["capability_build"],
            "opportunities_rejected": decision_counts["rejected"],
            "capability_gaps_created": len(payload["capability_gaps"]),
            "simple_mission_sources_refreshed": sorted(refreshed_ids),
            "simple_mission_opportunities_observed": sum(state.observed_count for _, state in source_results),
            "next_action": (
                "prepare_simple_mission_proposal_dossiers"
                if decision_counts["prepare_then_gate"]
                else "build_highest_priority_market_backed_capability"
                if payload["capability_gaps"]
                else "activate_next_authorized_official_source"
            ),
        }
    )
    evidence = list(cycle.get("evidence") or [])
    relative = str(RECEIPT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    receipt = {
        "schema_version": "1.0",
        "generated_at": payload["generated_at"],
        "sources": [
            {
                "source_id": state.source_id,
                "status": state.status,
                "reason": state.reason,
                "observed_count": state.observed_count,
                "evidence": list(state.evidence),
            }
            for _, state in source_results
        ],
        "opportunities_observed": sum(state.observed_count for _, state in source_results),
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
    }
    save_json(RECEIPT_PATH, receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
