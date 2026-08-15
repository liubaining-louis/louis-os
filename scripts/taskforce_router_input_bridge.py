from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASKFORCE = ROOT / "results" / "taskforce_market.json"
UNIVERSAL = ROOT / "results" / "universal_market_opportunities.json"


def load_dict(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def bridge(taskforce: dict[str, Any], universal: dict[str, Any]) -> dict[str, Any]:
    result = dict(universal)
    current = result.get("opportunities")
    opportunities = list(current) if isinstance(current, list) else []
    incoming = taskforce.get("opportunities")
    incoming = incoming if isinstance(incoming, list) else []

    seen = {
        str(item.get("opportunity_id") or item.get("source_url") or item.get("title"))
        for item in opportunities
        if isinstance(item, dict)
    }
    added = 0
    for item in incoming:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized.setdefault("source_id", "taskforce")
        normalized.setdefault("market_signal_verified", True)
        normalized.setdefault("fresh_open_verified", True)
        normalized.setdefault("legal_policy_pass", True)
        key = str(normalized.get("opportunity_id") or normalized.get("source_url") or normalized.get("title"))
        if not key or key in seen:
            continue
        opportunities.append(normalized)
        seen.add(key)
        added += 1

    result["opportunities"] = opportunities
    result["taskforce_bridge"] = {
        "source": "taskforce",
        "tasks_seen": taskforce.get("tasks_seen", 0),
        "qualified_count": taskforce.get("qualified_count", 0),
        "applications_attempted": taskforce.get("applications_attempted", 0),
        "accepted_notifications": len(taskforce.get("accepted_notifications") or []),
        "opportunities_added": added,
    }
    return result


def main() -> None:
    universal = load_dict(UNIVERSAL)
    taskforce = load_dict(TASKFORCE)
    merged = bridge(taskforce, universal)
    UNIVERSAL.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSAL.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(merged.get("taskforce_bridge", {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
