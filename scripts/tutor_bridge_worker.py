#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from atlas.tutor_bridge import run_tutor_cycle

ROOT = Path(__file__).resolve().parents[1]
INTERVAL = max(60, int(os.getenv("LOUIS_TUTOR_INTERVAL_SECONDS", "300")))


def main() -> int:
    run_once = os.getenv("LOUIS_TUTOR_RUN_ONCE", "0") == "1"
    while True:
        payload = run_tutor_cycle(ROOT)
        safe = {
            "status": payload.get("status"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "generated_at": payload.get("generated_at"),
            "reason": payload.get("reason"),
            "advice": payload.get("advice"),
        }
        print(json.dumps(safe, ensure_ascii=False), flush=True)
        if run_once:
            return 0 if payload.get("status") == "completed" else 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
