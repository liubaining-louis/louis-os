#!/usr/bin/env python3
"""Synchronize cash-first evidence and conservative operating economics."""
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
OPERATING_COSTS_PATH = RESULTS / "operating_costs.json"
DEFAULT_UNKNOWN_COSTS = ["gcp_compute", "model_api", "github_actions", "transaction_fees"]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _economic_cost_view(costs: Mapping[str, Any] | None) -> tuple[float, list[str], str]:
    if not costs:
        return 0.0, list(DEFAULT_UNKNOWN_COSTS), "incomplete_cost_basis"
    known = 0.0
    components = costs.get("components") if isinstance(costs.get("components"), Mapping) else {}
    unknown: list[str] = []
    for name in DEFAULT_UNKNOWN_COSTS:
        item = components.get(name) if isinstance(components, Mapping) else None
        if isinstance(item, Mapping) and item.get("known") is True:
            try:
                known += float(item.get("eur") or 0.0)
            except (TypeError, ValueError):
                unknown.append(name)
        else:
            unknown.append(name)
    return round(known, 6), unknown, "complete" if not unknown else "incomplete_cost_basis"


def synchronize(
    ledger: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    human: Mapping[str, Any],
    cycle: Mapping[str, Any],
    operating_costs: Mapping[str, Any] | None = None,
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

    result["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0)
    result["internet_actions_submitted"] = int(ledger.get("internet_actions_submitted") or 0)
    result["conversions"] = int(ledger.get("conversions") or 0)
    result["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    result["revenue_received"] = float(ledger.get("revenue_received") or 0.0)

    known_cost, unknown_components, cost_status = _economic_cost_view(operating_costs)
    result["known_operating_cost_eur"] = known_cost
    result["unknown_cost_components"] = unknown_components
    result["cost_basis_status"] = cost_status
    result["net_profit_eur"] = (
        round(result["revenue_confirmed_eur"] - known_cost, 6)
        if cost_status == "complete"
        else None
    )
    result["net_profit_policy"] = "Never claim net profit while any material operating-cost component is unknown."
    return result


def main() -> int:
    ledger = load_json(LEDGER_PATH, {})
    portfolio = load_json(PORTFOLIO_PATH, {})
    human = load_json(HUMAN_PATH, {})
    cycle = load_json(CYCLE_PATH, {})
    costs = load_json(OPERATING_COSTS_PATH, {})
    synchronized = synchronize(ledger, portfolio, human, cycle, costs)
    save_json(LEDGER_PATH, synchronized)
    print(
        json.dumps(
            {
                "cash_first_candidates": synchronized.get("cash_first_candidates", 0),
                "human_action_ready": synchronized.get("human_action_ready", 0),
                "external_actions_submitted": synchronized.get("external_actions_submitted", 0),
                "revenue_confirmed_eur": synchronized.get("revenue_confirmed_eur", 0.0),
                "known_operating_cost_eur": synchronized.get("known_operating_cost_eur", 0.0),
                "unknown_cost_components": synchronized.get("unknown_cost_components", []),
                "net_profit_eur": synchronized.get("net_profit_eur"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
