#!/usr/bin/env python3
"""Generate adaptive source metrics, recovery candidates and Opportunity Factory directives."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.cash_first_recovery import build_recovery_payload
from atlas.opportunity_factory import build_factory_plan

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
HISTORY_PATH = RESULTS / "opportunity_history.json"
RECOVERY_PATH = RESULTS / "cash_first_recovery.json"
FACTORY_PATH = RESULTS / "opportunity_factory_plan.json"
CAPABILITY_PATH = RESULTS / "capability_registry.json"
DEMO_RECEIPTS_PATH = RESULTS / "software_micro_mission_demo_receipts.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
LEDGER_PATH = RESULTS / "monetization.json"

# Only map capabilities that are directly evidenced by the validated demo artifact.
# This avoids treating the wider capability backlog as already executable.
DEMO_CAPABILITY_ALIASES = {
    "landing_page": ["landing_page", "static_website", "html_css_fix", "responsive_fix"],
    "csv_automation": ["csv_cleanup", "csv_deduplication", "python_file_automation", "data_format_cleanup"],
    "api_integration": ["api_debug", "python_script"],
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _existing_capabilities(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("validated_capabilities") or payload.get("capabilities") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("capability_id"):
            status = str(item.get("status") or item.get("capability_status") or "validated")
            if status in {"validated", "active", "tested"}:
                out.append(str(item["capability_id"]))
    return out


def _validated_demo_capabilities(payload: Any) -> list[str]:
    """Promote only capability aliases backed by a validated demo receipt."""
    if not isinstance(payload, dict):
        return []
    receipts = payload.get("receipts") or []
    if not isinstance(receipts, list):
        return []
    out: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict) or str(receipt.get("status")) != "validated":
            continue
        demo_id = str(receipt.get("demo_id") or "")
        out.extend(DEMO_CAPABILITY_ALIASES.get(demo_id, []))
    return list(dict.fromkeys(out))


def _current_allocation(ledger: dict[str, Any]) -> dict[str, float]:
    intelligence = ledger.get("mission_intelligence") if isinstance(ledger.get("mission_intelligence"), dict) else {}
    allocation = intelligence.get("search_allocation") if isinstance(intelligence.get("search_allocation"), dict) else {}
    return {
        "explicit_marketplaces": float(allocation.get("proven_sources", 0.0) or 0.0),
        "public_requests": float(allocation.get("adjacent_sources", 0.0) or 0.0),
        "proactive_problem_discovery": 0.0,
        "capability_experiments": float(allocation.get("experimental_sources", 0.0) or 0.0),
    }


def main() -> int:
    market = load_json(MARKET_PATH, {})
    history = load_json(HISTORY_PATH, {})
    ledger = load_json(LEDGER_PATH, {})
    capabilities = load_json(CAPABILITY_PATH, {})
    demo_receipts = load_json(DEMO_RECEIPTS_PATH, {})
    if not isinstance(market, dict) or not isinstance(history, dict):
        raise SystemExit("market and opportunity history must be valid JSON objects")
    if not isinstance(ledger, dict):
        ledger = {}

    payload = build_recovery_payload(market, history)
    save_json(RECOVERY_PATH, payload)

    validated_capabilities = list(dict.fromkeys(
        _existing_capabilities(capabilities) + _validated_demo_capabilities(demo_receipts)
    ))
    factory = build_factory_plan(
        ledger,
        existing_capabilities=validated_capabilities,
        current_allocation=_current_allocation(ledger),
    )
    save_json(FACTORY_PATH, factory)

    cycle = load_json(CYCLE_PATH, {})
    if not isinstance(cycle, dict):
        cycle = {}
    counts = payload["counts"]
    cycle.update({
        "cash_first_recovery_engine": "active",
        "opportunity_factory_engine": "active",
        "cash_first_recovery_candidates": counts["recovery_candidates"],
        "cash_first_sources_measured": counts["sources_measured"],
        "cash_first_search_directives": counts["directives"],
        "opportunity_factory_query_count": len(factory["query_pack"]),
        "opportunity_factory_capability_target": factory["capability_registry"]["target_count"],
        "opportunity_factory_missing_capabilities": len(factory["capability_registry"]["missing"]),
        "opportunity_factory_validated_capabilities": validated_capabilities,
        "opportunity_factory_cycle_targets": factory["cycle_targets"],
        "next_action": (
            "revalidate_best_historical_cash_first_candidate"
            if counts["recovery_candidates"]
            else "execute_opportunity_factory_query_pack"
        ),
    })
    evidence = list(cycle.get("evidence") or [])
    for path in (RECOVERY_PATH, FACTORY_PATH, DEMO_RECEIPTS_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence and path.exists():
            evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger.update({
        "cash_first_recovery_engine": "active",
        "opportunity_factory_engine": "active",
        "cash_first_recovery_candidates": counts["recovery_candidates"],
        "cash_first_sources_measured": counts["sources_measured"],
        "cash_first_search_directives": counts["directives"],
        "cash_first_recovery_top": payload["recovery_queue"][0] if payload["recovery_queue"] else None,
        "opportunity_factory_query_count": len(factory["query_pack"]),
        "opportunity_factory_allocation_target": factory["allocation"]["target"],
        "opportunity_factory_funnel_diagnosis": factory["funnel_diagnosis"],
        "opportunity_factory_cycle_targets": factory["cycle_targets"],
        "opportunity_factory_capability_target": factory["capability_registry"]["target_count"],
        "opportunity_factory_missing_capabilities": len(factory["capability_registry"]["missing"]),
        "opportunity_factory_validated_capabilities": validated_capabilities,
        "next_action": cycle["next_action"],
    })
    ledger["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0)
    ledger["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    save_json(LEDGER_PATH, ledger)

    print(json.dumps({
        "recovery_candidates": counts["recovery_candidates"],
        "sources_measured": counts["sources_measured"],
        "directives": counts["directives"],
        "factory_queries": len(factory["query_pack"]),
        "factory_validated_capabilities": len(validated_capabilities),
        "factory_missing_capabilities": len(factory["capability_registry"]["missing"]),
        "submitted": ledger["external_actions_submitted"],
        "revenue_eur": ledger["revenue_confirmed_eur"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
