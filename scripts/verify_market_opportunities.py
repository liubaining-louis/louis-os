#!/usr/bin/env python3
"""Apply the opportunity truth gate and emit a canonical verified snapshot."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.opportunity_truth_gate import verify_opportunity

INPUT = ROOT / "results" / "universal_market_opportunities.json"
OUTPUT = ROOT / "results" / "verified_market_opportunities.json"
CANONICAL = ROOT / "results" / "monetization_canonical.json"


def load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise SystemExit(f"invalid JSON object: {path}")
    return payload


def save(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    market = load(INPUT)
    raw = market.get("opportunities")
    if not isinstance(raw, list):
        raise SystemExit("market opportunities list is missing")

    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        result = verify_opportunity(item)
        record = dict(item)
        record["truth_gate"] = result.to_dict()
        if result.passed:
            verified.append(record)
        else:
            rejected.append(record)

    snapshot = {
        "schema_version": "1.0",
        "source_generated_at": market.get("generated_at"),
        "verified_count": len(verified),
        "rejected_count": len(rejected),
        "verified": verified,
        "rejected": rejected,
    }
    save(OUTPUT, snapshot)

    decision_counts = {
        "execute_now": 0,
        "prepare_then_gate": 0,
    }
    for item in verified:
        decision = item.get("decision")
        status = decision.get("status") if isinstance(decision, Mapping) else None
        if status in {"executable_now", "execute_now"}:
            decision_counts["execute_now"] += 1
        elif status == "prepare_then_gate":
            decision_counts["prepare_then_gate"] += 1

    canonical = {
        "schema_version": "1.0",
        "source_generated_at": market.get("generated_at"),
        "truth_gate_verified": len(verified),
        "truth_gate_rejected": len(rejected),
        "execute_now": decision_counts["execute_now"],
        "prepare_then_gate": decision_counts["prepare_then_gate"],
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
        "submission_blocked_stage": (
            "submission_executor" if sum(decision_counts.values()) else "opportunity_verification"
        ),
        "evidence": [str(OUTPUT.relative_to(ROOT))],
    }
    save(CANONICAL, canonical)
    print(json.dumps(canonical, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
