#!/usr/bin/env python3
"""Prioritize small paid missions and persist exact human-gate notifications."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.cash_first_market import (
    build_cash_first_portfolio,
    human_action_payload,
    prioritize_capability_backlog,
)

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
PORTFOLIO_PATH = RESULTS / "cash_first_market.json"
HUMAN_ACTION_PATH = RESULTS / "human_action_required.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
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


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, dict) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    previous_human = load_json(HUMAN_ACTION_PATH, {"items": []})
    previous_fingerprints = {
        str(item.get("notification_fingerprint") or "")
        for item in previous_human.get("items", [])
        if isinstance(item, dict) and item.get("notification_fingerprint")
    }

    portfolio = build_cash_first_portfolio(market)
    human = human_action_payload(portfolio)
    new_items = [
        item
        for item in human.get("items", [])
        if str(item.get("notification_fingerprint") or "") not in previous_fingerprints
    ]
    human["new_count"] = len(new_items)
    human["new_items"] = new_items
    human["notification_required"] = bool(new_items)
    backlog = prioritize_capability_backlog(load_json(BACKLOG_PATH, {"items": []}), portfolio)

    save_json(PORTFOLIO_PATH, portfolio)
    save_json(HUMAN_ACTION_PATH, human)
    save_json(BACKLOG_PATH, backlog)

    counts = portfolio["counts"]
    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "cash_first_candidates": counts["cash_first"],
            "strategic_candidates": counts["strategic"],
            "human_action_ready": counts["human_action_ready"],
            "new_human_actions": human["new_count"],
            "owner_notification_required": human["notification_required"],
            "cash_first_top_opportunity": portfolio.get("top_cash_first"),
            "next_action": (
                "notify_owner_and_complete_exact_human_gate"
                if human["notification_required"]
                else "route_top_cash_first_mission_to_executor"
                if counts["cash_first"]
                else "activate_next_small_mission_source"
            ),
        }
    )
    evidence = list(cycle.get("evidence") or [])
    for path in (PORTFOLIO_PATH, HUMAN_ACTION_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence:
            evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    ledger.update(
        {
            "cash_first_engine": "active",
            "cash_first_candidates": counts["cash_first"],
            "strategic_candidates": counts["strategic"],
            "human_action_ready": counts["human_action_ready"],
            "new_human_actions": human["new_count"],
            "owner_notification_required": human["notification_required"],
            "next_action": cycle["next_action"],
            "cash_first_top_opportunity": portfolio.get("top_cash_first"),
        }
    )
    save_json(LEDGER_PATH, ledger)

    print(
        json.dumps(
            {
                "cash_first": counts["cash_first"],
                "strategic": counts["strategic"],
                "human_action_ready": counts["human_action_ready"],
                "new_human_actions": human["new_count"],
                "next_action": cycle["next_action"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
