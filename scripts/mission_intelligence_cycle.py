#!/usr/bin/env python3
"""Run the Mission Intelligence Engine on canonical Louis OS evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.mission_intelligence import (
    IntelligencePolicy,
    allocate_search,
    build_outcome_metrics,
    detect_stagnation,
    score_mission,
)

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
HISTORY_PATH = RESULTS / "mission_outcome_history.json"
OUTPUT_PATH = RESULTS / "mission_intelligence.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
LEDGER_PATH = RESULTS / "monetization.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def event_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        values = payload.get("events") or payload.get("items") or []
    else:
        values = payload
    return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []


def days_without_progress(events: list[Mapping[str, Any]], now: datetime) -> int:
    timestamps: list[datetime] = []
    for item in events:
        if str(item.get("stage") or "") not in {"submitted", "replied", "won", "delivered", "accepted", "paid"}:
            continue
        raw = str(item.get("occurred_at") or item.get("timestamp") or "")
        try:
            timestamps.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not timestamps:
        return 999
    return max(0, (now - max(timestamps)).days)


def main() -> int:
    now = datetime.now(timezone.utc)
    policy = IntelligencePolicy()
    market = load_json(MARKET_PATH, {})
    opportunities = market.get("opportunities") if isinstance(market, Mapping) else []
    if not isinstance(opportunities, list):
        opportunities = []
    events = event_rows(load_json(HISTORY_PATH, {}))
    metrics = build_outcome_metrics(events)

    scored = []
    for opportunity in opportunities:
        if not isinstance(opportunity, Mapping):
            continue
        score = score_mission(opportunity, metrics, policy)
        if score is None:
            continue
        row = score.to_dict()
        row.update({
            "title": opportunity.get("title"),
            "source_id": opportunity.get("source_id"),
            "source_url": opportunity.get("source_url"),
            "reward_amount": opportunity.get("reward_amount"),
            "currency": opportunity.get("currency"),
        })
        scored.append(row)
    scored.sort(key=lambda item: (float(item["expected_value_per_hour_eur"]), float(item["expected_value_eur"])), reverse=True)

    stagnant_days = days_without_progress(events, now)
    stagnation = detect_stagnation(events, stagnant_days, policy)
    payload = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "objective": "maximize verified paid outcomes per delivery hour, human action and risk cost",
        "north_star_metric": "verified_revenue_eur / (delivery_hours + human_actions + risk_cost)",
        "counts": {
            "outcome_events": len(events),
            "market_opportunities": len(opportunities),
            "scored_cash_first_candidates": len(scored),
            "stagnation_triggers": len(stagnation),
        },
        "outcome_metrics": metrics,
        "search_allocation": allocate_search(metrics, policy),
        "stagnation": stagnation,
        "days_without_verified_progress": stagnant_days,
        "ranked_candidates": scored,
        "top_candidate": scored[0] if scored else None,
        "truth": {
            "forecasts_are_pipeline": False,
            "forecasts_are_revenue": False,
            "external_submissions_verified_added": 0,
            "revenue_verified_eur_added": 0.0,
            "evidence_required_for_submitted_and_later_stages": True,
        },
    }
    save_json(OUTPUT_PATH, payload)

    cycle = load_json(CYCLE_PATH, {})
    if not isinstance(cycle, dict):
        cycle = {}
    cycle.update({
        "mission_intelligence_engine": "active",
        "mission_intelligence_generated_at": payload["generated_at"],
        "mission_intelligence_candidates_scored": len(scored),
        "mission_intelligence_stagnation_triggers": len(stagnation),
        "mission_intelligence_next_action": (
            stagnation[0]["action"] if stagnation else "execute highest expected-value revalidated candidate"
        ),
    })
    evidence = list(cycle.get("evidence") or [])
    relative = str(OUTPUT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    if isinstance(ledger, dict):
        ledger["mission_intelligence"] = {
            "generated_at": payload["generated_at"],
            "top_candidate": payload["top_candidate"],
            "search_allocation": payload["search_allocation"],
            "stagnation": stagnation,
            "forecast_only": True,
        }
        save_json(LEDGER_PATH, ledger)

    print(json.dumps({
        "scored": len(scored),
        "stagnation_triggers": len(stagnation),
        "verified_submissions_added": 0,
        "verified_revenue_added_eur": 0.0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
