from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
TOKEN_PROGRAMS = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _rpc(method: str, params: list[Any]) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = Request(RPC_URL, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return payload.get("result")


def read_balances(address: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    lamports = int((_rpc("getBalance", [address, {"commitment": "confirmed"}]) or {}).get("value") or 0)
    result["SOL"] = {"raw": lamports, "decimals": 9, "amount": lamports / 1_000_000_000}
    for program_id in TOKEN_PROGRAMS:
        token_result = _rpc("getTokenAccountsByOwner", [address, {"programId": program_id}, {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
        for item in token_result.get("value") or []:
            info = (((item.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
            token = info.get("tokenAmount") or {}
            mint = str(info.get("mint") or "")
            if not mint:
                continue
            raw = int(token.get("amount") or 0)
            decimals = int(token.get("decimals") or 0)
            current = result.get(mint, {"raw": 0, "decimals": decimals, "amount": 0.0})
            current["raw"] = int(current.get("raw") or 0) + raw
            current["decimals"] = decimals
            current["amount"] = current["raw"] / (10 ** decimals if decimals else 1)
            result[mint] = current
    return result


def _stage(results: Path, received_events: list[dict[str, Any]]) -> tuple[str, str]:
    if received_events:
        return "ON_CHAIN_CONFIRMED", "monitor_next_crypto_opportunity"
    if (results / "superteam_submission_receipt.json").exists():
        return "SUBMITTED", "track_bounty_result_and_payout"
    candidates = _load(results / "superteam_candidates.json", {})
    if int(candidates.get("count") or 0) > 0:
        return "BUILDING", "build_and_submit_selected_bounty"
    accounts = _load(results / "platform_accounts.json", {}).get("accounts", {})
    wallet = _load(results / "crypto_wallet_public.json", {})
    if wallet.get("address") and any(isinstance(v, dict) and v.get("status") == "ready" for v in accounts.values()):
        return "ACCOUNT_READY", "discover_active_crypto_bounty"
    return "FOUND", "prepare_crypto_identity"


def run_crypto_revenue_cycle(root: Path) -> dict[str, Any]:
    results = root / "results"
    wallet = _load(results / "crypto_wallet_public.json", {})
    address = str(wallet.get("address") or "")
    state_path = results / "crypto_realization.json"
    previous = _load(state_path, {})
    previous_balances = previous.get("balances") if isinstance(previous.get("balances"), dict) else {}
    events = previous.get("received_events") if isinstance(previous.get("received_events"), list) else []
    if not address:
        payload = {"updated_at": _now(), "stage": "FOUND", "next_action": "bootstrap_crypto_wallet", "crypto_received": False, "received_events": events}
        _save(state_path, payload)
        return payload
    balances = read_balances(address)
    if previous_balances:
        for asset, current in balances.items():
            old_raw = int((previous_balances.get(asset) or {}).get("raw") or 0)
            new_raw = int(current.get("raw") or 0)
            if new_raw > old_raw:
                decimals = int(current.get("decimals") or 0)
                events.append({"detected_at": _now(), "chain": "solana", "asset": asset, "raw_delta": new_raw - old_raw, "amount": (new_raw - old_raw) / (10 ** decimals if decimals else 1), "on_chain_confirmed": True})
    stage, next_action = _stage(results, events)
    payload = {"updated_at": _now(), "stage": stage, "next_action": next_action, "wallet_address": address, "balances": balances, "crypto_received": bool(events), "received_events": events}
    _save(state_path, payload)
    return payload
