#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from atlas.superteam_crypto_cycle import run_superteam_crypto_cycle


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    try:
        outcome = run_superteam_crypto_cycle(ROOT)
    except Exception as exc:
        outcome = {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": f"{type(exc).__name__}:{exc}"[:500],
            "diagnosis": {
                "blocked_stage": "superteam_api_cycle",
                "next_action": "retry_next_autonomy_cycle",
            },
            "evidence": [],
        }
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, default=str))
    raise SystemExit(0 if str(outcome.get("status") or "failed") in {"completed", "blocked"} else 1)
