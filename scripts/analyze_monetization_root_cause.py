#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.monetization_root_cause import analyze_monetization

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load_json(name: str, default: Any) -> Any:
    try:
        return json.loads((RESULTS / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(name: str, value: Any) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    ledger = load_json("monetization.json", {})
    candidates = load_json("monetization_candidates.json", {"candidates": []}).get("candidates") or []
    actions = load_json("external_action_queue.json", {"actions": []}).get("actions") or []
    receipts = load_json("external_action_receipts.json", {"receipts": []}).get("receipts") or []

    diagnosis = analyze_monetization(
        ledger=ledger,
        candidates=candidates,
        external_actions=actions,
        external_receipts=receipts,
    ).to_dict()
    diagnosis["generated_at"] = now
    diagnosis["source_issue"] = 77
    diagnosis["evidence_files"] = [
        "results/monetization.json",
        "results/monetization_candidates.json",
        "results/external_action_queue.json",
        "results/external_action_receipts.json",
    ]
    save_json("monetization_root_cause.json", diagnosis)

    primary = diagnosis["primary_cause"]
    ledger.update(
        {
            "updated_at": now,
            "root_cause_code": primary["code"],
            "root_cause_confidence": primary["confidence"],
            "primary_blocker": primary["explanation"],
            "corrective_action": primary["corrective_action"],
            "root_cause_success_metric": primary["success_metric"],
            "time_to_first_euro_band": diagnosis["time_to_first_euro_band"],
            "next_action": primary["corrective_action"],
        }
    )
    save_json("monetization.json", ledger)
    print(json.dumps({"status": "diagnosed", "primary_cause": primary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
