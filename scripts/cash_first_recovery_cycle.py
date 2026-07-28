#!/usr/bin/env python3
"""Generate adaptive source metrics, recovery candidates and search directives."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.cash_first_recovery import build_recovery_payload

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
HISTORY_PATH = RESULTS / "opportunity_history.json"
RECOVERY_PATH = RESULTS / "cash_first_recovery.json"
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
    history = load_json(HISTORY_PATH, {})
    if not isinstance(market, dict) or not isinstance(history, dict):
        raise SystemExit("market and opportunity history must be valid JSON objects")

    payload = build_recovery_payload(market, history)
    save_json(RECOVERY_PATH, payload)

    cycle = load_json(CYCLE_PATH, {})
    if not isinstance(cycle, dict):
        cycle = {}
    counts = payload["counts"]
    cycle.update({
        "cash_first_recovery_engine": "active",
        "cash_first_recovery_candidates": counts["recovery_candidates"],
        "cash_first_sources_measured": counts["sources_measured"],
        "cash_first_search_directives": counts["directives"],
        "next_action": (
            "revalidate_best_historical_cash_first_candidate"
            if counts["recovery_candidates"]
            else "execute_adaptive_search_directives"
        ),
    })
    evidence = list(cycle.get("evidence") or [])
    relative = str(RECOVERY_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    if not isinstance(ledger, dict):
        ledger = {}
    ledger.update({
        "cash_first_recovery_engine": "active",
        "cash_first_recovery_candidates": counts["recovery_candidates"],
        "cash_first_sources_measured": counts["sources_measured"],
        "cash_first_search_directives": counts["directives"],
        "cash_first_recovery_top": payload["recovery_queue"][0] if payload["recovery_queue"] else None,
        "next_action": cycle["next_action"],
    })
    ledger["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0)
    ledger["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    save_json(LEDGER_PATH, ledger)

    print(json.dumps({
        "recovery_candidates": counts["recovery_candidates"],
        "sources_measured": counts["sources_measured"],
        "directives": counts["directives"],
        "submitted": ledger["external_actions_submitted"],
        "revenue_eur": ledger["revenue_confirmed_eur"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
