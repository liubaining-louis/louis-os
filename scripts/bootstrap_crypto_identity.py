#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from atlas.crypto_identity import ensure_solana_wallet, register_platform_account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-dir", default="/app/runtime-secrets")
    parser.add_argument("--results-dir", default="/app/results")
    args = parser.parse_args()

    secret_dir = Path(args.secret_dir)
    results_dir = Path(args.results_dir)
    wallet = ensure_solana_wallet(secret_dir, results_dir)
    account = register_platform_account(
        results_dir,
        platform="superteam",
        email=os.getenv("LOUIS_ACCOUNT_EMAIL", "").strip(),
        account_ref=os.getenv("SUPERTEAM_AGENT_NAME", "louis-os-agent").strip() or "louis-os-agent",
        auth_material_present=bool(os.getenv("SUPERTEAM_API_KEY", "").strip()),
    )
    print(json.dumps({
        "wallet": {"chain": wallet.get("chain"), "address": wallet.get("address"), "receive_enabled": True},
        "platform_account": {"platform": account.get("platform"), "status": account.get("status"), "email": account.get("email")},
        "private_key_output": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
