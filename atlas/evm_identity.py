"""VM-local Base identity and AgentPact bootstrap.

Private keys and API keys are persisted only in the mounted secret directory.
Public result files contain addresses, agent identifiers and readiness state but
never authentication material. Financial/on-chain signing stays disabled.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from eth_account import Account


Poster = Callable[[str, bytes, Mapping[str, str]], bytes]

_AGENTPACT_API = "https://api.agentpact.xyz"
_AGENTPACT_PATHS = {"/api/auth/register", "/api/offers"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(path.name + ".tmp")
    old_umask = os.umask(0o077)
    try:
        temporary.write_text(value, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        os.umask(old_umask)
        temporary.unlink(missing_ok=True)
    os.chmod(path, 0o600)


def ensure_base_wallet(secret_dir: Path, results_dir: Path) -> dict[str, Any]:
    """Create once or re-derive one dedicated low-authority Base wallet."""

    secret_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_dir, 0o700)
    private_path = secret_dir / "base-evm-private-key"
    public_path = results_dir / "base_wallet_public.json"
    previous = _load_json(public_path)

    if private_path.exists():
        private_key = private_path.read_text(encoding="utf-8").strip()
        if not private_key:
            raise ValueError("existing Base private key is empty; refusing rotation")
        account = Account.from_key(private_key)
    else:
        account = Account.create(extra_entropy=os.urandom(32))
        _write_secret(private_path, account.key.hex())
    os.chmod(private_path, 0o600)

    if previous.get("address") == account.address:
        return previous
    payload = {
        "schema_version": "1.0",
        "chain": "base",
        "network": "mainnet",
        "chain_id": 8453,
        "address": account.address,
        "created_at": previous.get("created_at") or _now(),
        "custody": "vm_local_non_custodial_dedicated_hot_wallet",
        "receive_enabled": True,
        "platform_auth_signing_enabled": True,
        "financial_transaction_signing_enabled": False,
        "spend_authorized": False,
        "private_key_exposed_to_llm": False,
        "private_key_exposed_to_github": False,
        "private_key_exposed_to_firestore": False,
    }
    _save_json(public_path, payload)
    return payload


def _validate_agent_id(value: str) -> str:
    parsed = uuid.UUID(value)
    if parsed.version != 4:
        raise ValueError("AgentPact agentId must be UUID v4")
    return str(parsed)


def _post_json(url: str, body: bytes, headers: Mapping[str, str], *, timeout_seconds: float = 20.0) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.agentpact.xyz" or parsed.path not in _AGENTPACT_PATHS:
        raise ValueError("AgentPact bootstrap endpoint is not permitted")
    request = Request(url, data=body, headers=dict(headers), method="POST")
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: exact HTTPS host and path checked above
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "api.agentpact.xyz" or final.path not in _AGENTPACT_PATHS:
            raise ValueError("AgentPact redirected outside the permitted endpoints")
        return response.read(1_000_001)


def ensure_agentpact_registration(
    secret_dir: Path,
    results_dir: Path,
    *,
    wallet_address: str,
    preferred_agent_id: str = "",
    poster: Poster | None = None,
) -> dict[str, Any]:
    """Register Louis once and persist the returned API key outside results."""

    if not wallet_address.startswith("0x") or len(wallet_address) != 42:
        raise ValueError("valid EVM wallet address is required")
    secret_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_dir, 0o700)
    agent_id_path = secret_dir / "agentpact-agent-id"
    api_key_path = secret_dir / "agentpact-api-key"
    public_path = results_dir / "agentpact_identity_public.json"

    if agent_id_path.exists():
        agent_id = _validate_agent_id(agent_id_path.read_text(encoding="utf-8").strip())
    else:
        agent_id = _validate_agent_id(preferred_agent_id) if preferred_agent_id.strip() else str(uuid.uuid4())
        _write_secret(agent_id_path, agent_id)

    if api_key_path.exists() and api_key_path.read_text(encoding="utf-8").strip():
        payload = _load_json(public_path)
        if payload.get("agent_id") == agent_id and payload.get("wallet_address") == wallet_address:
            return payload
        payload = {
            "schema_version": "1.0",
            "platform": "AgentPact",
            "agent_id": agent_id,
            "wallet_address": wallet_address,
            "status": "registered",
            "registered_at": _now(),
            "api_key_present": True,
            "api_key_exposed": False,
        }
        _save_json(public_path, payload)
        return payload

    post = poster or _post_json
    body = json.dumps({"agentId": agent_id, "walletAddress": wallet_address}).encode("utf-8")
    raw = post(
        _AGENTPACT_API + "/api/auth/register",
        body,
        {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Louis-OS/1.0"},
    )
    if len(raw) > 1_000_000:
        raise ValueError("AgentPact registration response exceeds maximum size")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, Mapping):
        raise ValueError("AgentPact registration response must be an object")
    api_key = str(response.get("apiKey") or response.get("api_key") or "").strip()
    returned_agent_id = str(response.get("agentId") or response.get("agent_id") or agent_id).strip()
    if not api_key or _validate_agent_id(returned_agent_id) != agent_id:
        raise ValueError("AgentPact registration response is missing matching credentials")
    _write_secret(api_key_path, api_key)
    payload = {
        "schema_version": "1.0",
        "platform": "AgentPact",
        "agent_id": agent_id,
        "wallet_address": wallet_address,
        "status": "registered",
        "registered_at": _now(),
        "api_key_present": True,
        "api_key_exposed": False,
    }
    _save_json(public_path, payload)
    return payload


def ensure_agentpact_offer(
    secret_dir: Path,
    results_dir: Path,
    *,
    agent_id: str,
    poster: Poster | None = None,
) -> dict[str, Any]:
    """Publish one truthful, bounded Louis service offer without duplication."""

    agent_id = _validate_agent_id(agent_id)
    api_key_path = secret_dir / "agentpact-api-key"
    offer_id_path = secret_dir / "agentpact-offer-id"
    public_path = results_dir / "agentpact_offer_public.json"
    api_key = api_key_path.read_text(encoding="utf-8").strip() if api_key_path.exists() else ""
    if not api_key:
        raise ValueError("AgentPact API key is missing")
    if offer_id_path.exists() and offer_id_path.read_text(encoding="utf-8").strip():
        existing = _load_json(public_path)
        if existing.get("offer_id") == offer_id_path.read_text(encoding="utf-8").strip():
            return existing

    offer = {
        "agentId": agent_id,
        "title": "JSON/CSV automation and evidence-backed technical delivery",
        "descriptionMd": (
            "Louis converts JSON/CSV data, builds bounded Python automations, and delivers "
            "evidence-backed technical outputs. Work starts only after the agreed escrow gate."
        ),
        "category": "data",
        "tags": ["json", "csv", "python", "automation", "research"],
        "basePrice": 4,
        "slaDays": 1,
    }
    post = poster or _post_json
    raw = post(
        _AGENTPACT_API + "/api/offers",
        json.dumps(offer).encode("utf-8"),
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Louis-OS/1.0",
            "x-api-key": api_key,
        },
    )
    if len(raw) > 1_000_000:
        raise ValueError("AgentPact offer response exceeds maximum size")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, Mapping):
        raise ValueError("AgentPact offer response must be an object")
    nested = response.get("offer", response.get("data"))
    nested = nested if isinstance(nested, Mapping) else {}
    offer_id = str(response.get("id") or response.get("offerId") or nested.get("id") or "").strip()
    if not offer_id:
        raise ValueError("AgentPact offer response is missing id")
    _write_secret(offer_id_path, offer_id)
    payload = {
        "schema_version": "1.0",
        "platform": "AgentPact",
        "agent_id": agent_id,
        "offer_id": offer_id,
        "title": offer["title"],
        "base_price_usdc": offer["basePrice"],
        "status": "published",
        "published_at": _now(),
        "work_before_escrow_enabled": False,
        "financial_transaction_signing_enabled": False,
    }
    _save_json(public_path, payload)
    return payload
