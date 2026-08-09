#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from atlas.crypto_identity import ensure_solana_wallet, register_platform_account
from atlas.evm_identity import ensure_agentpact_offer, ensure_agentpact_registration, ensure_base_wallet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-dir", default="/app/runtime-secrets")
    parser.add_argument("--results-dir", default="/app/results")
    args = parser.parse_args()

    secret_dir = Path(args.secret_dir)
    results_dir = Path(args.results_dir)
    email = os.getenv("LOUIS_ACCOUNT_EMAIL", "").strip()
    solana_wallet = ensure_solana_wallet(secret_dir, results_dir)
    base_wallet = ensure_base_wallet(secret_dir, results_dir)
    superteam = register_platform_account(
        results_dir,
        platform="superteam",
        email=email,
        account_ref=os.getenv("SUPERTEAM_AGENT_NAME", "louis-os-agent").strip() or "louis-os-agent",
        auth_material_present=bool(os.getenv("SUPERTEAM_API_KEY", "").strip()),
    )

    agentpact_identity: dict[str, object]
    agentpact_offer: dict[str, object]
    try:
        agentpact_identity = ensure_agentpact_registration(
            secret_dir,
            results_dir,
            wallet_address=str(base_wallet["address"]),
            preferred_agent_id=os.getenv("AGENTPACT_AGENT_ID", "").strip(),
        )
        agentpact = register_platform_account(
            results_dir,
            platform="agentpact",
            email=email,
            account_ref=str(agentpact_identity.get("agent_id") or ""),
            auth_material_present=bool(agentpact_identity.get("api_key_present")),
        )
        try:
            agentpact_offer = ensure_agentpact_offer(
                secret_dir,
                results_dir,
                agent_id=str(agentpact_identity["agent_id"]),
            )
        except Exception as exc:
            agentpact_offer = {"status": "blocked", "reason": f"{type(exc).__name__}:{exc}"[:500]}
    except Exception as exc:
        agentpact_identity = {"status": "needs_auth", "reason": f"{type(exc).__name__}:{exc}"[:500]}
        agentpact_offer = {"status": "blocked", "reason": "agentpact_registration_not_ready"}
        agentpact = register_platform_account(
            results_dir,
            platform="agentpact",
            email=email,
            account_ref=os.getenv("AGENTPACT_AGENT_ID", "").strip(),
            auth_material_present=False,
        )

    bountybook = register_platform_account(
        results_dir,
        platform="bountybook",
        email=email,
        account_ref=str(base_wallet["address"]),
        auth_material_present=(secret_dir / "base-evm-private-key").exists(),
    )
    result = {
        "wallets": {
            "solana": {
                "chain": solana_wallet.get("chain"),
                "address": solana_wallet.get("address"),
                "receive_enabled": True,
            },
            "base": {
                "chain": base_wallet.get("chain"),
                "address": base_wallet.get("address"),
                "receive_enabled": True,
                "financial_transaction_signing_enabled": False,
                "spend_authorized": False,
            },
        },
        "platform_accounts": {
            "superteam": {"status": superteam.get("status"), "account_ref": superteam.get("account_ref")},
            "bountybook": {"status": bountybook.get("status"), "account_ref": bountybook.get("account_ref")},
            "agentpact": {"status": agentpact.get("status"), "account_ref": agentpact.get("account_ref")},
        },
        "agentpact_identity": {
            "status": agentpact_identity.get("status"),
            "agent_id": agentpact_identity.get("agent_id"),
        },
        "agentpact_offer": {
            "status": agentpact_offer.get("status"),
            "offer_id": agentpact_offer.get("offer_id"),
            "reason": agentpact_offer.get("reason"),
        },
        "private_key_output": False,
        "api_key_output": False,
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "agent_market_bootstrap.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
