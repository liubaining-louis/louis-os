#!/usr/bin/env python3
"""Build transferable playbooks from structured Internet success evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.best_practice_learning import SuccessEvidence, build_playbook, learning_manifest

INPUT = ROOT / "results" / "internet_success_evidence.json"
OUTPUT = ROOT / "results" / "best_practice_playbooks.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> int:
    raw = load_json(INPUT, {"items": []})
    rows = []
    for item in raw.get("items", []):
        try:
            rows.append(SuccessEvidence(**item))
        except (TypeError, ValueError):
            continue
    mechanisms = sorted({item.mechanism for item in rows if item.mechanism})
    playbooks = [build_playbook(mechanism, rows) for mechanism in mechanisms]
    payload = learning_manifest(playbooks)
    payload["input_evidence_count"] = len(rows)
    payload["instruction"] = (
        "Use experiment-ready playbooks only for small reversible tests; keep all other playbooks as research hypotheses."
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
