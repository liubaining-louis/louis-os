#!/usr/bin/env python3
"""Reject payer-incompatible, ineligible and sensitive missions before routing."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.automation_compatibility import reject_incompatible_delivery_methods

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
RECEIPT_PATH = RESULTS / "delivery_compatibility_receipt.json"


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

    rows, rejected = reject_incompatible_delivery_methods(
        [item for item in market["opportunities"] if isinstance(item, Mapping)]
    )
    market["opportunities"] = rows
    save_json(MARKET_PATH, market)

    rejected_items = []
    reason_counts: dict[str, int] = {}
    for item in rows:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        reason = str(metadata.get("policy_rejection") or "")
        if not reason:
            continue
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        rejected_items.append(
            {
                "opportunity_id": item.get("opportunity_id"),
                "title": item.get("title"),
                "source_url": item.get("source_url"),
                "reason": reason,
            }
        )

    receipt = {
        "schema_version": "1.1",
        "generated_at": market.get("generated_at"),
        "rejected_count": rejected,
        "reason_counts": dict(sorted(reason_counts.items())),
        "items": rejected_items,
        "capability_gaps_created": 0,
        "human_actions_created": 0,
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
    }
    save_json(RECEIPT_PATH, receipt)

    cycle = load_json(CYCLE_PATH, {})
    cycle["policy_incompatible_opportunities_rejected"] = rejected
    cycle["ai_prohibited_opportunities_rejected"] = reason_counts.get("automation_prohibited_by_payer", 0)
    cycle["unverifiable_eligibility_opportunities_rejected"] = reason_counts.get("unverifiable_personal_eligibility", 0)
    cycle["sensitive_record_opportunities_rejected"] = reason_counts.get("sensitive_personal_records_request", 0)
    evidence = list(cycle.get("evidence") or [])
    relative = str(RECEIPT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
