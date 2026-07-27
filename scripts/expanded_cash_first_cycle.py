#!/usr/bin/env python3
"""Expand cash-first discovery and preserve an append-only opportunity registry."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.expanded_market_sources import (
    ExpandedFreelancerPublicJobsSource,
    ExpandedSoftwareFreelancerPublicJobsSource,
)
from atlas.universal_market import CapabilityRegistry, InternetOpportunity, SourceState, UniversalMarketEngine

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
HISTORY_PATH = RESULTS / "opportunity_history.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
RECEIPT_PATH = RESULTS / "expanded_source_refresh.json"
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


def lifecycle_status(item: Mapping[str, Any]) -> str:
    decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
    status = str(decision.get("status") or "observed")
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    if metadata.get("external_receipt") or metadata.get("externally_submitted"):
        return "submitted"
    if status == "rejected":
        return "rejected"
    if status == "prepare_then_gate":
        return "prepared"
    if status == "executable_now":
        return "executable"
    if status == "capability_build":
        return "capability_build"
    return "observed"


def merge_history(history: Mapping[str, Any], current: list[Mapping[str, Any]], generated_at: str) -> dict[str, Any]:
    existing = {
        str(item.get("opportunity_id") or ""): dict(item)
        for item in history.get("items") or []
        if isinstance(item, Mapping) and str(item.get("opportunity_id") or "")
    }
    current_ids: set[str] = set()
    for raw in current:
        opportunity_id = str(raw.get("opportunity_id") or "")
        if not opportunity_id:
            continue
        current_ids.add(opportunity_id)
        prior = existing.get(opportunity_id, {})
        first_seen = prior.get("first_seen_at") or raw.get("observed_at") or generated_at
        snapshots = list(prior.get("snapshots") or [])
        snapshots.append(
            {
                "observed_at": generated_at,
                "status": lifecycle_status(raw),
                "reward_amount": raw.get("reward_amount"),
                "currency": raw.get("currency"),
                "deadline": raw.get("deadline"),
                "source_url": raw.get("source_url"),
            }
        )
        existing[opportunity_id] = {
            "opportunity_id": opportunity_id,
            "title": raw.get("title"),
            "source_id": raw.get("source_id"),
            "source_url": raw.get("source_url"),
            "first_seen_at": first_seen,
            "last_seen_at": generated_at,
            "lifecycle_status": lifecycle_status(raw),
            "active_in_latest_cycle": True,
            "latest": dict(raw),
            "snapshots": snapshots[-48:],
        }
    for opportunity_id, item in existing.items():
        if opportunity_id not in current_ids:
            item["active_in_latest_cycle"] = False
            if item.get("lifecycle_status") not in {"submitted", "rejected", "expired", "closed"}:
                item["lifecycle_status"] = "not_seen_current_cycle"
    rows = sorted(existing.values(), key=lambda item: (not bool(item.get("active_in_latest_cycle")), str(item.get("last_seen_at") or "")), reverse=False)
    counts: dict[str, int] = {}
    for item in rows:
        key = str(item.get("lifecycle_status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "retention_policy": "append-only by opportunity_id; absent items are retained with an explicit lifecycle status",
        "count": len(rows),
        "active_count": sum(bool(item.get("active_in_latest_cycle")) for item in rows),
        "counts_by_status": counts,
        "items": rows,
    }


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, Mapping) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    opportunities = [opportunity_from_dict(item) for item in market.get("opportunities", []) if isinstance(item, Mapping)]
    existing_states = [source_state_from_dict(item) for item in market.get("source_states", []) if isinstance(item, Mapping)]
    source_results = [
        ExpandedFreelancerPublicJobsSource(maximum_results=120).collect(),
        ExpandedSoftwareFreelancerPublicJobsSource(maximum_results=100).collect(),
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

    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    history = merge_history(load_json(HISTORY_PATH, {}), [item for item in payload.get("opportunities", []) if isinstance(item, Mapping)], generated_at)
    save_json(HISTORY_PATH, history)

    receipt = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "sources": [
            {"source_id": state.source_id, "status": state.status, "reason": state.reason, "observed_count": state.observed_count, "evidence": list(state.evidence)}
            for _, state in source_results
        ],
        "expanded_categories": 32,
        "opportunities_observed": sum(state.observed_count for _, state in source_results),
        "history_count": history["count"],
        "history_active_count": history["active_count"],
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
    }
    save_json(RECEIPT_PATH, receipt)

    cycle = load_json(CYCLE_PATH, {})
    cycle.update({
        "generated_at": generated_at,
        "expanded_source_engine": "active",
        "expanded_source_categories": 32,
        "expanded_source_opportunities_observed": receipt["opportunities_observed"],
        "opportunity_history_count": history["count"],
        "opportunity_history_active_count": history["active_count"],
        "opportunity_retention_policy": "append_only_with_explicit_lifecycle_status",
    })
    evidence = list(cycle.get("evidence") or [])
    for path in (HISTORY_PATH, RECEIPT_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence:
            evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
