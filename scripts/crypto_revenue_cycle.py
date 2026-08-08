#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from atlas.crypto_revenue import run_crypto_revenue_cycle

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    print(json.dumps(run_crypto_revenue_cycle(ROOT), sort_keys=True))
