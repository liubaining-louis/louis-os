from __future__ import annotations

import json
from pathlib import Path

from atlas.opportunity_factory import build_factory_plan

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    monetization = read_json(RESULTS / "monetization.json")
    capabilities = read_json(RESULTS / "capability_registry.json")
    existing = capabilities.get("validated_capabilities") or capabilities.get("capabilities") or []
    if existing and isinstance(existing[0] if isinstance(existing, list) else None, dict):
        existing = [item.get("capability_id") for item in existing if isinstance(item, dict) and item.get("capability_id")]

    intelligence = monetization.get("mission_intelligence") if isinstance(monetization.get("mission_intelligence"), dict) else {}
    allocation = intelligence.get("search_allocation") if isinstance(intelligence.get("search_allocation"), dict) else {}
    current_allocation = {
        "explicit_marketplaces": float(allocation.get("proven_sources", 0.0) or 0.0),
        "public_requests": float(allocation.get("adjacent_sources", 0.0) or 0.0),
        "proactive_problem_discovery": 0.0,
        "capability_experiments": float(allocation.get("experimental_sources", 0.0) or 0.0),
    }

    payload = build_factory_plan(
        monetization,
        existing_capabilities=existing,
        current_allocation=current_allocation,
    )
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "opportunity_factory_plan.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out.relative_to(ROOT)),
        "queries": len(payload["query_pack"]),
        "missing_capabilities": len(payload["capability_registry"]["missing"]),
        "diagnoses": len(payload["funnel_diagnosis"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
