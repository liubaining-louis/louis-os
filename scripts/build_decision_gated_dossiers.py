from __future__ import annotations

import json
from pathlib import Path

from atlas.decision_gated_dossiers import build_pipeline

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
INPUT = RESULTS / "verified_market_opportunities.json"
OUTPUT = RESULTS / "decision_gated_dossiers.json"


def _load_items() -> list[dict]:
    try:
        payload = json.loads(INPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("verified", "opportunities", "items", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    output = build_pipeline(_load_items())
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(OUTPUT.relative_to(ROOT)),
        "prepare_then_gate": output["prepare_then_gate"],
        "external_submissions_verified": output["external_submissions_verified"],
    }))


if __name__ == "__main__":
    main()
