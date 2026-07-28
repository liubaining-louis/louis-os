#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.internet_experience_learning import InternetObservation, OutcomeFeedback, learning_directives, synthesize_claims

RESULTS = ROOT / "results"
OBSERVATIONS_PATH = RESULTS / "internet_observations.json"
OUTCOMES_PATH = RESULTS / "mission_outcome_memory.json"
OUTPUT_PATH = RESULTS / "internet_experience_learning.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    raw_observations = load_json(OBSERVATIONS_PATH, {"items": []})
    raw_outcomes = load_json(OUTCOMES_PATH, {"items": []})
    observations = [InternetObservation(**item) for item in raw_observations.get("items", []) if isinstance(item, Mapping)]
    outcomes = [OutcomeFeedback(**item) for item in raw_outcomes.get("items", []) if isinstance(item, Mapping)]
    claims = synthesize_claims(observations, outcomes)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "objective": "learn from public Internet evidence and verified outcomes without confusing repetition with truth",
        "counts": {
            "observations": len(observations),
            "claims": len(claims),
            "supported_or_validated": sum(row["promotion_level"] in {"supported", "validated"} for row in claims),
            "verified_outcomes": len(outcomes),
        },
        "claims": claims,
        "directives": learning_directives(claims),
        "truth": {
            "internet_claims_are_revenue": False,
            "external_submissions_verified_added": 0,
            "revenue_verified_eur_added": 0.0,
            "canonical_revalidation_required_for_time_sensitive_claims": True,
        },
    }
    save_json(OUTPUT_PATH, payload)
    cycle = load_json(CYCLE_PATH, {})
    cycle.update({
        "internet_experience_learning": "active",
        "internet_learning_claims": len(claims),
        "internet_learning_supported_or_validated": payload["counts"]["supported_or_validated"],
        "internet_learning_updated_at": generated_at,
    })
    evidence = list(cycle.get("evidence") or [])
    relative = str(OUTPUT_PATH.relative_to(ROOT))
    if relative not in evidence:
        evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)
    print(json.dumps(payload["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
