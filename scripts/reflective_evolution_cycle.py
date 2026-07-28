#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.reflective_evolution import diagnose, review_previous

RESULTS = ROOT / "results"
OUTPUT = RESULTS / "reflective_evolution.json"
HISTORY = RESULTS / "reflective_evolution_history.json"


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_metrics() -> dict[str, Any]:
    market = load(RESULTS / "universal_market_opportunities.json", {})
    cash = load(RESULTS / "cash_first_market.json", {})
    ledger = load(RESULTS / "monetization.json", {})
    submissions = load(RESULTS / "submission_receipts.json", {})
    intelligence = load(RESULTS / "mission_intelligence.json", {})

    opportunities = market.get("opportunities") or []
    source_states = market.get("source_states") or []
    decisions = [item.get("decision", {}) for item in opportunities if isinstance(item, dict)]
    return {
        "opportunities_observed": len(opportunities),
        "opportunities_eligible": sum(str(d.get("status")) in {"executable_now", "prepare_then_gate"} for d in decisions),
        "opportunities_rejected": sum(str(d.get("status")) == "rejected" for d in decisions),
        "dossiers_prepared": int((cash.get("counts") or {}).get("prepared", cash.get("prepared_count", 0)) or 0),
        "external_submissions_verified": int(ledger.get("external_actions_submitted", submissions.get("external_submissions_verified", 0)) or 0),
        "replies_verified": int(ledger.get("replies_verified", 0) or 0),
        "missions_won_verified": int(ledger.get("missions_won_verified", 0) or 0),
        "revenue_verified_eur": float(ledger.get("revenue_confirmed_eur", ledger.get("revenue_verified_eur", 0.0)) or 0.0),
        "sources_total": len(source_states),
        "mission_intelligence_available": bool(intelligence),
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    metrics = collect_metrics()
    prior = load(OUTPUT, {})
    diagnosis = diagnose(metrics, now=now)
    review = review_previous(prior.get("diagnosis") if isinstance(prior, dict) else None, metrics)
    payload = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "objective": "see clearly, correct root causes with balance, and raise global system vision",
        "metacognition_claim": "disciplined evidence-based self-evaluation; not consciousness or emotion",
        "metrics": metrics,
        "previous_action_review": review,
        "diagnosis": diagnosis.to_dict(),
        "cycle_contract": {
            "one_principal_weakness": True,
            "root_cause_before_patch": True,
            "bounded_reversible_action": True,
            "preserve_validated_capabilities": True,
            "measure_before_claiming_improvement": True,
        },
        "truth": {
            "external_submissions_verified_added": 0,
            "revenue_verified_eur_added": 0.0,
            "sentience_claimed": False,
        },
    }
    save(OUTPUT, payload)

    history = load(HISTORY, {"schema_version": "1.0", "items": []})
    items = list(history.get("items") or [])
    items.append({
        "generated_at": payload["generated_at"],
        "weakness_id": diagnosis.weakness_id,
        "weakness_class": diagnosis.weakness_class,
        "principal_weakness": diagnosis.principal_weakness,
        "corrective_action": diagnosis.corrective_action,
        "success_metric": diagnosis.success_metric,
        "previous_action_review": review,
    })
    history["items"] = items[-168:]
    history["generated_at"] = payload["generated_at"]
    save(HISTORY, history)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
