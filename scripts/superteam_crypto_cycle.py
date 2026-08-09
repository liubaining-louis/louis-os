#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from atlas.superteam_crypto_cycle import run_superteam_crypto_cycle


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    outcome = run_superteam_crypto_cycle(ROOT)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, default=str))
    raise SystemExit(0 if str(outcome.get("status") or "failed") in {"completed", "blocked"} else 1)
