#!/usr/bin/env python3
"""Fail closed on stale, closed or non-canonical platform bounty issues."""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.github_issue_verifier import verify_open_issues
from atlas.universal_market import CapabilityRegistry, InternetOpportunity, SourceState, UniversalMarketEngine

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
RECEIPT_PATH = RESULTS / "small_bounty_source_refresh.json"
CAPABILITIES_PATH = ROOT / "config" / "universal_capabilities.json"
PLATFORM_SOURCES = {"algora_public_bounties", "opire_public_bounties"}


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
            "## Acceptance tests",
            *[f"- [ ] {value}" for value in specification.get("acceptance_tests") or []],
            "",
            "No external submission or revenue claim is authorized without a verified open issue and receipt.",
        ]
    )
    return {"title": f"Capability gap: {capability_id}", "body": body, "marker": marker}


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, Mapping) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    all_rows = [opportunity_from_dict(item) for item in market["opportunities"] if isinstance(item, Mapping)]
    platform_rows = [item for item in all_rows if item.source_id in PLATFORM_SOURCES]
    other_rows = [item for item in all_rows if item.source_id not in PLATFORM_SOURCES]
    verified_rows, rejected_count = verify_open_issues(platform_rows)

    states = [source_state_from_dict(item) for item in market.get("source_states", []) if isinstance(item, Mapping)]
    verified_by_source = {source_id: 0 for source_id in PLATFORM_SOURCES}
    for item in verified_rows:
        verified_by_source[item.source_id] += 1
    corrected_states: list[SourceState] = []
    for state in states:
        if state.source_id not in PLATFORM_SOURCES:
            corrected_states.append(state)
            continue
        count = verified_by_source[state.source_id]
        corrected_states.append(
            SourceState(
                source_id=state.source_id,
                category=state.category,
                status="ok" if count else "empty",
                reason=f"Canonical GitHub validation rejected {state.observed_count - count} stale, closed or unverifiable entries.",
                evidence=state.evidence,
                observed_count=count,
            )
        )

    evaluation = UniversalMarketEngine(CapabilityRegistry.from_file(CAPABILITIES_PATH)).evaluate(
        [*other_rows, *verified_rows], corrected_states
    )
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
            "items": [{**gap, "issue": issue} for gap, issue in zip(payload["capability_gaps"], issue_payloads, strict=True)],
        },
    )

    cycle = load_json(CYCLE_PATH, {})
    counts = payload["decision_counts"]
    cycle.update(
        {
            "generated_at": payload["generated_at"],
            "opportunities_observed": len(payload["opportunities"]),
            "opportunities_executable_now": counts["executable_now"],
            "opportunities_prepare_then_gate": counts["prepare_then_gate"],
            "opportunities_capability_build": counts["capability_build"],
            "opportunities_rejected": counts["rejected"],
            "capability_gaps_created": len(payload["capability_gaps"]),
            "small_bounty_opportunities_observed": len(verified_rows),
            "small_bounty_issue_state_rejected": rejected_count,
            "next_action": (
                "route_executable_opportunities_to_verified_executor"
                if counts["executable_now"]
                else "build_highest_priority_market_backed_capability"
                if payload["capability_gaps"]
                else "refresh_capability_specific_verified_sources"
            ),
        }
    )
    save_json(CYCLE_PATH, cycle)

    receipt = load_json(RECEIPT_PATH, {})
    receipt.update(
        {
            "generated_at": payload["generated_at"],
            "opportunities_observed": len(verified_rows),
            "canonical_issue_state_verified": len(verified_rows),
            "canonical_issue_state_rejected": rejected_count,
            "external_submissions_verified": 0,
            "revenue_verified_eur": 0.0,
        }
    )
    save_json(RECEIPT_PATH, receipt)
    print(json.dumps({"verified": len(verified_rows), "rejected": rejected_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
