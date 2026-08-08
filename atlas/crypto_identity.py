from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BASE58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def base58_encode(raw: bytes) -> str:
    if not raw:
        return ""
    zeros = 0
    for value in raw:
        if value != 0:
            break
        zeros += 1
    number = int.from_bytes(raw, "big")
    encoded = bytearray()
    while number:
        number, rem = divmod(number, 58)
        encoded.append(_BASE58[rem])
    encoded.reverse()
    return (_BASE58[:1] * zeros + encoded).decode("ascii")


def solana_address_from_spki_der(der: bytes) -> str:
    if len(der) != len(_ED25519_SPKI_PREFIX) + 32 or not der.startswith(_ED25519_SPKI_PREFIX):
        raise ValueError("unexpected Ed25519 SubjectPublicKeyInfo encoding")
    return base58_encode(der[-32:])


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_solana_wallet(secret_dir: Path, results_dir: Path) -> dict[str, Any]:
    secret_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_dir, 0o700)
    private_path = secret_dir / "solana-ed25519-private.pem"
    public_path = results_dir / "crypto_wallet_public.json"

    if private_path.exists() and public_path.exists():
        payload = json.loads(public_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("address"):
            return payload

    old_umask = os.umask(0o077)
    try:
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        os.umask(old_umask)
    os.chmod(private_path, 0o600)

    pub = subprocess.run(
        ["openssl", "pkey", "-in", str(private_path), "-pubout", "-outform", "DER"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    address = solana_address_from_spki_der(pub)
    payload = {
        "schema_version": "1.0",
        "chain": "solana",
        "network": "mainnet-beta",
        "address": address,
        "created_at": _now(),
        "custody": "vm_local_non_custodial",
        "receive_enabled": True,
        "outbound_signing_enabled": False,
        "private_key_exposed_to_llm": False,
        "private_key_exposed_to_github": False,
        "private_key_exposed_to_firestore": False,
    }
    _save_json(public_path, payload)
    return payload


def register_platform_account(
    results_dir: Path,
    *,
    platform: str,
    email: str,
    account_ref: str,
    auth_material_present: bool,
) -> dict[str, Any]:
    path = results_dir / "platform_accounts.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {"schema_version": "1.0", "accounts": {}}
    if not isinstance(current, dict):
        current = {"schema_version": "1.0", "accounts": {}}
    accounts = current.get("accounts")
    if not isinstance(accounts, dict):
        accounts = {}
        current["accounts"] = accounts
    accounts[platform] = {
        "platform": platform,
        "email": email,
        "account_ref": account_ref,
        "status": "ready" if auth_material_present else "needs_auth",
        "auth_material_present": bool(auth_material_present),
        "secrets_stored_in_registry": False,
        "updated_at": _now(),
    }
    current["updated_at"] = _now()
    _save_json(path, current)
    return accounts[platform]
