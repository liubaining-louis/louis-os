from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from atlas.paid_mission_apprenticeship import coach

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "universal_market_cycle.json"
OUTPUT = ROOT / "results" / "paid_mission_apprenticeship.json"
DOSSIERS = ROOT / "results" / "simple_mission_dossiers"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def proposal_is_ready(opportunity: Dict[str, Any]) -> bool:
    artifacts: List[str] = opportunity.get("prepared_artifacts") or []
    if not artifacts:
        return False
    return all((ROOT / path).exists() for path in artifacts)


def build_record(market: Dict[str, Any]) -> Dict[str, Any]:
    opportunity = market.get("cash_first_top_opportunity") or {}
    record: Dict[str, Any] = {
        "opportunity_id": opportunity.get("opportunity_id"),
        "title": opportunity.get("title"),
        "source_url": opportunity.get("source_url"),
        "qualified": bool(opportunity) and opportunity.get("decision_status") in {"prepare_then_gate", "execute_now"},
        "proposal_ready": proposal_is_ready(opportunity),
        "payment_method": (opportunity.get("payment_methods") or [None])[0],
        "estimated_effort_hours": opportunity.get("estimated_effort_hours"),
        "estimated_hourly_value": opportunity.get("estimated_hourly_value"),
        "human_gate_required": opportunity.get("human_gate_required", False),
        "human_actions": opportunity.get("human_actions") or [],
        "prepared_artifacts": opportunity.get("prepared_artifacts") or [],
        "external_submission_verified": False,
        "revenue_verified_eur": 0.0,
    }
    return record


def main() -> None:
    market = load_json(INPUT)
    record = build_record(market)
    decision = coach(record)
    selected = bool(record.get("opportunity_id"))
    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "move one truthful opportunity through proposal, delivery, acceptance and verified payment",
        "selected": selected,
        "mission": record if selected else None,
        "coaching": decision.__dict__ if selected else {
            "stage": "none",
            "next_action": "refresh narrow capability-matched sources",
            "owner": "louis_os",
            "missing_evidence": ["eligible_cash_first_opportunity"],
            "stop_condition": "do not manufacture a mission",
            "risk": "false progress",
            "countermeasure": "retain zero-state truth",
        },
        "human_action_packet": {
            "required": bool(selected and record.get("human_gate_required") and decision.owner == "human_or_louis_os"),
            "actions": record.get("human_actions", []) if selected else [],
            "instruction": "Use a truthful platform account, review terms, submit the prepared proposal, and return the external submission receipt. Do not claim submission without that receipt.",
        },
        "truth": {
            "external_submission_verified": False,
            "mission_won_verified": False,
            "delivery_verified": False,
            "payment_verified": False,
            "revenue_verified_eur": 0.0,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
