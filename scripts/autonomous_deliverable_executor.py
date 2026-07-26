#!/usr/bin/env python3
"""Run one evidence-backed internal monetization deliverable cycle."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.monetization_execution_cycle import run_verified_deliverable_cycle


def main() -> int:
    outcome = run_verified_deliverable_cycle(ROOT)
    print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome.get("status") in {"completed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
