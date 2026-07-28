from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from atlas.first_paid_mission import evaluate
from atlas.paid_mission_apprenticeship import coach

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "universal_market_cycle.json"
OUTPUT = ROOT / "results" / "paid_mission_apprenticeship.json"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def proposal_is_ready(opportunity: Dict[str, Any]) -> bool:
    artifacts: List[str] = opportunity.get("prepared_artifacts") or []
    if not artifacts:
        return False
    return all((ROOT / path).exists() for path in artifacts)


def accelerator_input(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a market candidate into the strict first-paid-mission contract."""
    human_actions = opportunity.get("human_actions") or []
    evidence = opportunity.get("evidence") or []
    reward = opportunity.get("reward_eur")
    if reward is None and str(opportunity.get("currency", "")).upper() == "EUR":
        reward = opportunity.get("reward_amount")

    return {
        "title": opportunity.get("title"),
        "description": " ".join(str(x) for x in evidence),
        "skills": opportunity.get("skills") or [],
        "category": opportunity.get("lane"),
        "fresh_open_verified": opportunity.get("fresh_open_verified") is True,
        "payment_path": (opportunity.get("payment_methods") or [None])[0],
        "acceptance_criteria": opportunity.get("acceptance_criteria"),
        "effort_hours": opportunity.get("estimated_effort_hours", 999),
        "capability_fit": opportunity.get("capability_fit", 0.0),
        "personal_eligibility_required": opportunity.get("personal_eligibility_required", False),
        "active_competing_claim": opportunity.get("active_competing_claim", False),
        "legal_policy_pass": opportunity.get("legal_policy_pass") is True,
        "human_actions_required": len(human_actions),
        "reward_eur": reward or 0.0,
        "payment_confidence": opportunity.get("payment_confidence", 0.0),
        "competition_risk": opportunity.get("competition_risk", 0.5),
    }


def build_record(market: Dict[str, Any]) -> Dict[str, Any]:
    opportunity = market.get("cash_first_top_opportunity") or {}
    gate = evaluate(accelerator_input(opportunity)) if opportunity else None
    eligible = bool(gate and gate.eligible)

    record: Dict[str, Any] = {
        "opportunity_id": opportunity.get("opportunity_id"),
        "title": opportunity.get("title"),
        "source_url": opportunity.get("source_url"),
        "qualified": eligible,
        "proposal_ready": eligible and proposal_is_ready(opportunity),
        "payment_method": (opportunity.get("payment_methods") or [None])[0],
        "estimated_effort_hours": opportunity.get("estimated_effort_hours"),
        "estimated_hourly_value": opportunity.get("estimated_hourly_value"),
        "human_gate_required": opportunity.get("human_gate_required", False),
        "human_actions": opportunity.get("human_actions") or [],
        "prepared_artifacts": opportunity.get("prepared_artifacts") or [],
        "accelerator_gate": {
            "eligible": bool(gate and gate.eligible),
            "reasons": list(gate.reasons) if gate else ["no_candidate"],
            "score": gate.score if gate else 0.0,
            "recommended_offer": gate.recommended_offer if gate else None,
        },
        "external_submission_verified": False,
        "revenue_verified_eur": 0.0,
    }
    return record


def main() -> None:
    market = load_json(INPUT)
    record = build_record(market)
    selected = bool(record.get("opportunity_id") and record["accelerator_gate"]["eligible"])
    decision = coach(record) if selected else None
    output = {
        "schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "move one strictly eligible opportunity through proposal, delivery, acceptance and verified payment",
        "selected": selected,
        "rejected_candidate": None if selected or not record.get("opportunity_id") else record,
        "mission": record if selected else None,
        "coaching": decision.__dict__ if selected else {
            "stage": "none",
            "next_action": "refresh narrow sources using first-paid-mission hard gates",
            "owner": "louis_os",
            "missing_evidence": record.get("accelerator_gate", {}).get("reasons", ["eligible_cash_first_opportunity"]),
            "stop_condition": "do not prepare, submit or claim progress on an ineligible mission",
            "risk": "low-value work or false progress",
            "countermeasure": "apply the accelerator before proposal preparation and coaching",
        },
        "human_action_packet": {
            "required": bool(selected and record.get("human_gate_required") and decision and decision.owner == "human_or_louis_os"),
            "actions": record.get("human_actions", []) if selected else [],
            "instruction": "Use a truthful platform account, review terms, submit the prepared proposal, and return the external submission receipt. Do not claim submission without that receipt." if selected else "No human action: candidate failed the first-paid-mission gate.",
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
