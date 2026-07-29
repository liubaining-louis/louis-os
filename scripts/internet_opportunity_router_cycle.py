from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.internet_opportunity_router import next_pivot, route_all

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "universal_market_cycle.json"
OUTPUT = ROOT / "results" / "internet_opportunity_router.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def extract_items(market: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in (
        "opportunities",
        "items",
        "market_opportunities",
        "simple_mission_opportunities",
        "universal_market_opportunities",
    ):
        value = market.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    top = market.get("cash_first_top_opportunity")
    if isinstance(top, dict) and top:
        candidates.append(top)
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = str(item.get("opportunity_id") or item.get("source_url") or item.get("title") or len(deduped))
        deduped[key] = item
    return list(deduped.values())


def build_cycle(market: dict[str, Any]) -> dict[str, Any]:
    items = extract_items(market)
    routed = route_all(items)
    decisions = {name: 0 for name in ("execute_now", "prepare_then_gate", "capability_build", "reject")}
    domains: dict[str, dict[str, int]] = {}
    for item in routed:
        state = item["internet_opportunity_router"]
        decisions[state["decision"]] += 1
        domain = state["domain"]
        domains.setdefault(domain, {"seen": 0, "eligible": 0, "execute_now": 0, "prepare_then_gate": 0, "capability_build": 0, "reject": 0})
        domains[domain]["seen"] += 1
        domains[domain][state["decision"]] += 1
        if state["decision"] in {"execute_now", "prepare_then_gate"}:
            domains[domain]["eligible"] += 1

    metrics = {
        "rejected_without_candidate": decisions["reject"] if not decisions["execute_now"] and not decisions["prepare_then_gate"] else 0,
        "source_results_without_eligible": int(market.get("scout_items_rejected", 0)) if not decisions["execute_now"] and not decisions["prepare_then_gate"] else 0,
        "proposals_without_reply": max(0, int(market.get("outreach_sent", 0)) - int(market.get("qualified_replies", 0))),
        "replies_without_conversion": max(0, int(market.get("qualified_replies", 0)) - int(market.get("conversions", 0))),
        "verified_payments": 1 if float(market.get("revenue_received", 0) or 0) > 0 else 0,
    }
    pivot = next_pivot(metrics)
    selected = next((item for item in routed if item["internet_opportunity_router"]["decision"] == "execute_now"), None)
    if selected is None:
        selected = next((item for item in routed if item["internet_opportunity_router"]["decision"] == "prepare_then_gate"), None)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "adaptive multidomain Internet opportunity discovery and execution",
        "allocation": {"exploit": 0.50, "adjacent": 0.30, "experimental": 0.20},
        "items_seen": len(items),
        "decision_counts": decisions,
        "domain_metrics": domains,
        "selected": selected,
        "top_ranked": routed[:10],
        "pivot_metrics": metrics,
        "next_pivot": pivot,
        "next_action": (
            "prepare execution dossier for selected opportunity"
            if selected
            else "regenerate capability-specific queries across under-tested domains and replace low-yield sources"
        ),
        "truth": {
            "external_submission_verified": False,
            "payment_verified": False,
            "revenue_verified_eur": float(market.get("revenue_received", 0) or 0),
            "forecast_only_not_pipeline_or_revenue": True,
        },
    }


def main() -> None:
    output = build_cycle(load_json(INPUT))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
