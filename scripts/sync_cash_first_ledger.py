#!/usr/bin/env python3
"""Synchronize dedicated cash-first evidence into the shared monetization ledger.

The autonomous submission workflow owns commits to results/monetization.json. This
script therefore runs there, after discovery workflows have persisted their own
artifacts, and never modifies revenue or submission counters without receipts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
LEDGER_PATH = RESULTS / "monetization.json"
PORTFOLIO_PATH = RESULTS / "cash_first_market.json"
HUMAN_PATH = RESULTS / "human_action_required.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def synchronize(
    ledger: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    human: Mapping[str, Any],
    cycle: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(ledger)
    counts = portfolio.get("counts") if isinstance(portfolio.get("counts"), Mapping) else {}
    generated_at = str(
        cycle.get("generated_at")
        or portfolio.get("generated_at")
        or human.get("generated_at")
        or result.get("updated_at")
        or ""
    )
    top = portfolio.get("top_cash_first") if isinstance(portfolio.get("top_cash_first"), Mapping) else None

    result.update(
        {
            "updated_at": generated_at,
            "cash_first_engine": "active",
            "cash_first_candidates": int(counts.get("cash_first") or 0),
            "strategic_candidates": int(counts.get("strategic") or 0),
            "human_action_ready": int(counts.get("human_action_ready") or 0),
            "new_human_actions": int(human.get("new_count") or 0),
            "owner_notification_required": bool(human.get("notification_required")),
            "cash_first_top_opportunity": dict(top) if top else None,
            "simple_mission_sources_refreshed": list(cycle.get("simple_mission_sources_refreshed") or []),
            "simple_mission_opportunities_observed": int(cycle.get("simple_mission_opportunities_observed") or 0),
            "simple_mission_dossiers_prepared": int(cycle.get("simple_mission_dossiers_prepared") or 0),
            "software_micro_mission_engine": str(cycle.get("software_micro_mission_engine") or "inactive"),
            "software_micro_mission_capability_count": int(cycle.get("software_micro_mission_capability_count") or 0),
            "software_micro_mission_validated_demo_count": int(cycle.get("software_micro_mission_validated_demo_count") or 0),
            "software_micro_missions_matched": int(cycle.get("software_micro_missions_matched") or 0),
            "software_micro_missions_accepted": int(cycle.get("software_micro_missions_accepted") or 0),
            "software_micro_missions_rejected": int(cycle.get("software_micro_missions_rejected") or 0),
            "software_micro_mission_dossiers_prepared": int(cycle.get("software_micro_mission_dossiers_prepared") or 0),
            "next_action": str(cycle.get("next_action") or result.get("next_action") or "activate_next_small_mission_source"),
        }
    )

    # Preserve economic truth. Discovery and dossier preparation cannot increment
    # these fields; only separate receipt-backed submission/payment paths may do so.
    result["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0)
    result["internet_actions_submitted"] = int(ledger.get("internet_actions_submitted") or 0)
    result["conversions"] = int(ledger.get("conversions") or 0)
    result["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    result["revenue_received"] = float(ledger.get("revenue_received") or 0.0)
    return result


def main() -> int:
    ledger = load_json(LEDGER_PATH, {})
    portfolio = load_json(PORTFOLIO_PATH, {})
    human = load_json(HUMAN_PATH, {})
    cycle = load_json(CYCLE_PATH, {})
    synchronized = synchronize(ledger, portfolio, human, cycle)
    save_json(LEDGER_PATH, synchronized)
    print(
        json.dumps(
            {
                "cash_first_candidates": synchronized.get("cash_first_candidates", 0),
                "human_action_ready": synchronized.get("human_action_ready", 0),
                "software_micro_mission_capability_count": synchronized.get("software_micro_mission_capability_count", 0),
                "software_micro_missions_accepted": synchronized.get("software_micro_missions_accepted", 0),
                "software_micro_mission_dossiers_prepared": synchronized.get("software_micro_mission_dossiers_prepared", 0),
                "external_actions_submitted": synchronized.get("external_actions_submitted", 0),
                "revenue_confirmed_eur": synchronized.get("revenue_confirmed_eur", 0.0),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
