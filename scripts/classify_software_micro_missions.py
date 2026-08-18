#!/usr/bin/env python3
"""Classify public freelance listings into bounded software micro-missions."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.software_micro_missions import assess_software_scope, classify_software_capability
from atlas.universal_market import CapabilityRegistry, InternetOpportunity, SourceState, UniversalMarketEngine

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
RECEIPT_PATH = RESULTS / "software_micro_mission_classification.json"
CAPABILITIES_PATH = ROOT / "config" / "universal_capabilities.json"

_VENDOR_WORKSPACE_PATTERNS = (
    re.compile(r"\bsmartsheet\b", re.I),
    re.compile(r"\bairtable\b", re.I),
    re.compile(r"\bmonday\.com\b", re.I),
    re.compile(r"\bclickup\b", re.I),
    re.compile(r"\bnotion\s+(?:workspace|database|automation)\b", re.I),
)


def unvalidated_vendor_workspace_reason(title: str, description: str = "") -> str | None:
    """Reject vendor-specific builds unless a dedicated capability exists.

    Generic web/code capabilities cannot truthfully satisfy requests for a working
    SaaS workspace, vendor dashboard or platform-native automation.
    """
    text = f"{title}\n{description}"
    if any(pattern.search(text) for pattern in _VENDOR_WORKSPACE_PATTERNS):
        return "unvalidated_vendor_specific_workspace"
    return None


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


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, Mapping) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    transformed: list[InternetOpportunity] = []
    rejected_reasons: dict[str, str] = {}
    matched = 0
    accepted = 0
    rejected = 0

    for raw in market.get("opportunities", []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        metadata = dict(item.get("metadata") or {})
        if metadata.get("source_kind") == "public_freelance_listing":
            title = str(item.get("title") or "")
            description = str(item.get("description") or "")
            vendor_reason = unvalidated_vendor_workspace_reason(title, description)
            assessment = (
                {"matched": True, "accepted": False, "reason": vendor_reason}
                if vendor_reason
                else assess_software_scope(title, description)
            )
            if assessment.get("matched"):
                matched += 1
                metadata["software_micro_mission"] = True
                metadata["software_scope_assessment"] = dict(assessment)
                if assessment.get("accepted"):
                    accepted += 1
                    capability = str(assessment["capability_id"])
                    item["required_capabilities"] = [capability]
                    metadata.update(
                        {
                            "estimated_effort_hours": float(assessment["estimated_effort_hours"]),
                            "software_capability_id": capability,
                            "software_deliverable_family": assessment["deliverable_family"],
                            "software_acceptance_checks": list(assessment["acceptance_checks"]),
                            "software_boundaries": list(assessment["boundaries"]),
                            "price_guidance_eur": list(assessment["price_guidance_eur"]),
                            "price_guidance_status": "internal_guidance_only_not_client_quote",
                        }
                    )
                else:
                    rejected += 1
                    capability = classify_software_capability(title, description) or "vendor_specific_workspace_delivery"
                    item["required_capabilities"] = [capability]
                    metadata["software_capability_id"] = capability
                    metadata["capability_gap_allowed"] = False
                    rejected_reasons[str(item.get("opportunity_id") or "")] = str(assessment.get("reason") or "software_scope_rejected")
        item["metadata"] = metadata
        transformed.append(opportunity_from_dict(item))

    states = [
        source_state_from_dict(item)
        for item in market.get("source_states", [])
        if isinstance(item, Mapping)
    ]
    payload = UniversalMarketEngine(CapabilityRegistry.from_file(CAPABILITIES_PATH)).evaluate(transformed, states).to_dict()
    payload["mission_prompt"] = market.get("mission_prompt")
    payload["mission_prompt_sha256"] = market.get("mission_prompt_sha256")

    for item in payload.get("opportunities", []):
        opportunity_id = str(item.get("opportunity_id") or "")
        reason = rejected_reasons.get(opportunity_id)
        if not reason:
            continue
        decision = dict(item.get("decision") or {})
        blockers = [str(value) for value in decision.get("blockers") or []]
        blocker = f"software_scope_rejected:{reason}"
        if blocker not in blockers:
            blockers.append(blocker)
        decision.update(
            {
                "status": "rejected",
                "missing_capabilities": [],
                "blockers": blockers,
                "next_action": "reject_and_continue_software_discovery",
                "human_action_minimal": "none",
            }
        )
        metadata = dict(item.get("metadata") or {})
        metadata["policy_rejection"] = reason
        metadata["capability_gap_allowed"] = False
        item["decision"] = decision
        item["metadata"] = metadata

    counts = {status: 0 for status in ("executable_now", "prepare_then_gate", "capability_build", "rejected")}
    for item in payload.get("opportunities", []):
        status = str((item.get("decision") or {}).get("status") or "rejected")
        counts[status] = counts.get(status, 0) + 1
    payload["decision_counts"] = counts
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(MARKET_PATH, payload)

    values = list(rejected_reasons.values())
    receipt = {
        "schema_version": "1.0",
        "generated_at": payload["generated_at"],
        "matched_count": matched,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "rejection_reasons": {reason: values.count(reason) for reason in sorted(set(values))},
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
    }
    save_json(RECEIPT_PATH, receipt)

    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "generated_at": payload["generated_at"],
            "software_micro_missions_matched": matched,
            "software_micro_missions_accepted": accepted,
            "software_micro_missions_rejected": rejected,
            "opportunities_executable_now": counts.get("executable_now", 0),
            "opportunities_prepare_then_gate": counts.get("prepare_then_gate", 0),
            "opportunities_capability_build": counts.get("capability_build", 0),
            "opportunities_rejected": counts.get("rejected", 0),
        }
    )
    if accepted:
        cycle["next_action"] = "prepare_and_rank_software_micro_mission_dossiers"
    evidence = list(cycle.get("evidence") or [])
    relative = str(RECEIPT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
