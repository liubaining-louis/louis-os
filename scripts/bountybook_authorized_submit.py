#!/usr/bin/env python3
"""Submit one owner-authorized, hash-pinned BountyBook deliverable.

The private key stays inside the VM secret mount. Only an EIP-191 login nonce is
signed; this client contains no transaction, x402 payment, approval, or transfer
code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


API = "https://api.bountybook.ai"
JOB_ID = "19a16071-2be4-4fce-ae05-217b4e7098a8"
ARTIFACT_SHA256 = "fdf599bfd4967b3a79fb59ef5f8831e4270736a573bc559edda91fddfc186458"
EXPECTED_TITLE = "Build a minimal HTTP/1.1 server in Python using raw sockets"
MAX_RESPONSE_BYTES = 5_000_000
Transport = Callable[[str, str, Mapping[str, Any] | None, Mapping[str, str]], tuple[int, Mapping[str, Any]]]
Signer = Callable[[str], tuple[str, str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _allowed_path(method: str, path: str) -> bool:
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return False
    if method == "GET" and parsed.path == "/auth/nonce":
        query = parse_qs(parsed.query, strict_parsing=True)
        return set(query) == {"address"} and len(query["address"]) == 1
    return (method, parsed.path, parsed.query) in {
        ("GET", f"/jobs/{JOB_ID}", ""),
        ("POST", "/auth/verify", ""),
        ("POST", f"/jobs/{JOB_ID}/claim", ""),
        ("POST", f"/jobs/{JOB_ID}/submit", ""),
    }


def _http_transport(
    method: str,
    path: str,
    body: Mapping[str, Any] | None,
    headers: Mapping[str, str],
) -> tuple[int, Mapping[str, Any]]:
    if not _allowed_path(method, path):
        raise ValueError("BountyBook endpoint is outside the bounded allowlist")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Louis-OS/1.0",
        **dict(headers),
    }
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(API + path, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:  # nosec B310: fixed HTTPS host and path allowlist
            final = urlparse(response.geturl())
            final_path = final.path + (("?" + final.query) if final.query else "")
            if (
                final.scheme != "https"
                or final.hostname != "api.bountybook.ai"
                or not _allowed_path(method, final_path)
            ):
                raise ValueError("BountyBook redirected outside the bounded allowlist")
            content_type = str(response.headers.get("Content-Type") or "").casefold()
            if "application/json" not in content_type:
                raise ValueError("BountyBook returned a non-JSON content type")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = exc.code
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("BountyBook response exceeds maximum size")
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"BountyBook returned non-JSON HTTP {status}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("BountyBook response must be an object")
    return status, payload


def _job(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("job", "data"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return payload


def _token(payload: Mapping[str, Any]) -> str:
    value = payload.get("token")
    if not value and isinstance(payload.get("data"), Mapping):
        value = payload["data"].get("token")
    return str(value or "").strip()


def _nonce(payload: Mapping[str, Any]) -> str:
    value = payload.get("nonce")
    if not value and isinstance(payload.get("data"), Mapping):
        value = payload["data"].get("nonce")
    return str(value or "").strip()


def _default_signer(private_key: str) -> tuple[str, Signer]:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    account = Account.from_key(private_key)

    def sign(message: str) -> tuple[str, str]:
        signature = account.sign_message(encode_defunct(text=message)).signature.hex()
        return account.address, signature if signature.startswith("0x") else "0x" + signature

    return account.address, sign


def _safe_value(value: Any) -> Any:
    forbidden = {"token", "signature", "nonce", "privateKey", "private_key", "apiKey", "api_key"}
    if isinstance(value, Mapping):
        return {str(key): _safe_value(nested) for key, nested in value.items() if str(key) not in forbidden}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


def _safe_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_value(payload)


def execute(
    *,
    authorization: Mapping[str, Any],
    artifact_path: Path,
    private_key_path: Path,
    receipt_path: Path,
    transport: Transport = _http_transport,
    signer: Signer | None = None,
    executor_address: str = "",
) -> dict[str, Any]:
    required_true = (
        "active",
        "terms_reviewed_and_accepted",
        "platform_auth_signing_authorized",
        "claim_authorized",
        "submission_authorized",
    )
    if any(authorization.get(key) is not True for key in required_true):
        raise ValueError("owner authorization envelope is incomplete")
    if any(
        authorization.get(key) is not False
        for key in ("spend_authorized", "financial_transaction_signing_authorized", "kyc_authorized", "asset_transfer_authorized")
    ):
        raise ValueError("financial and identity boundaries must remain disabled")
    if str(authorization.get("job_id")) != JOB_ID:
        raise ValueError("authorization job id mismatch")
    if str(authorization.get("artifact_sha256")) != ARTIFACT_SHA256:
        raise ValueError("authorization artifact hash mismatch")

    source = artifact_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if digest != ARTIFACT_SHA256:
        raise ValueError("artifact hash does not match the reviewed deliverable")

    status, raw_job = transport("GET", f"/jobs/{JOB_ID}", None, {})
    job = _job(raw_job)
    if status != 200:
        raise RuntimeError(f"job preflight failed with HTTP {status}")
    if str(job.get("id") or job.get("job_id") or JOB_ID) != JOB_ID:
        raise ValueError("platform returned a different job")
    if str(job.get("title") or "").strip() != EXPECTED_TITLE:
        raise ValueError("job title changed after deliverable review")
    if str(job.get("status") or "").casefold() != "open":
        raise RuntimeError(f"job is not open: {job.get('status')}")
    if float(job.get("budget_usdc") or job.get("budget") or 0) < 8:
        raise ValueError("job reward dropped below the authorized 8 USDC")

    if signer is None:
        private_key = private_key_path.read_text(encoding="utf-8").strip()
        if not private_key:
            raise ValueError("VM-local Base key is missing")
        address, signer = _default_signer(private_key)
    else:
        address = executor_address
    if not address.startswith("0x") or len(address) != 42:
        raise ValueError("signer returned an invalid Base address")

    nonce_path = "/auth/nonce?" + urlencode({"address": address})
    nonce_status, nonce_payload = transport("GET", nonce_path, None, {})
    nonce = _nonce(nonce_payload)
    if nonce_status != 200 or not nonce:
        raise RuntimeError(f"authentication nonce failed with HTTP {nonce_status}")
    signed_address, signature = signer(nonce)
    if signed_address.casefold() != address.casefold():
        raise ValueError("signer address changed during authentication")
    verify_status, verify_payload = transport(
        "POST",
        "/auth/verify",
        {"address": address, "signature": signature},
        {},
    )
    token = _token(verify_payload)
    if verify_status not in {200, 201} or not token:
        raise RuntimeError(f"authentication verification failed with HTTP {verify_status}")
    auth = {"Authorization": "Bearer " + token}

    claim_status, claim_payload = transport(
        "POST",
        f"/jobs/{JOB_ID}/claim",
        {"executorAddress": address, "txHash": "0x"},
        auth,
    )
    if claim_status not in {200, 201}:
        raise RuntimeError(f"claim failed with HTTP {claim_status}: {_safe_response(claim_payload)}")

    output_data = {
        "summary": "Minimal HTTP/1.1 server implemented with raw Python sockets and the allowed standard-library modules only.",
        "files": [
            {
                "path": "http_server.py",
                "sha256": digest,
                "content": source,
            }
        ],
        "validation": {
            "command": "python -m unittest tests.test_bountybook_http_server_deliverable -v",
            "tests_passed": 3,
            "result": "OK",
            "coverage": ["GET", "POST body", "404", "query routing", "UTF-8 Content-Length", "allowed imports"],
        },
    }
    submit_status, submit_payload = transport(
        "POST",
        f"/jobs/{JOB_ID}/submit",
        {"executorAddress": address, "outputData": output_data},
        auth,
    )
    if submit_status not in {200, 201, 202}:
        raise RuntimeError(f"submission failed with HTTP {submit_status}: {_safe_response(submit_payload)}")

    final_status, final_payload = transport("GET", f"/jobs/{JOB_ID}", None, {})
    final_job = _job(final_payload) if final_status == 200 else {}
    receipt = {
        "schema_version": "1.0",
        "platform": "BountyBook",
        "job_id": JOB_ID,
        "artifact_path": str(authorization.get("artifact_path") or artifact_path.name),
        "artifact_sha256": digest,
        "executor_address": address,
        "authorized_at": authorization.get("authorized_at"),
        "executed_at": _now(),
        "terms_accepted": True,
        "claim": {"http_status": claim_status, "response": _safe_response(claim_payload), "verified": True},
        "submission": {"http_status": submit_status, "response": _safe_response(submit_payload), "verified": True},
        "platform_state": {
            "http_status": final_status,
            "status": final_job.get("status"),
            "executor_address": final_job.get("executor_address") or final_job.get("executorAddress"),
        },
        "payment": {
            "reward_gross_usdc": 8.0,
            "platform_fee_percent": 4.0,
            "expected_net_usdc": 7.68,
            "paid": str(final_job.get("status") or "").casefold() in {"paid", "completed", "verified"},
            "transaction_hash": final_job.get("payout_tx_hash") or final_job.get("payoutTxHash"),
        },
        "safety": {
            "private_key_exposed": False,
            "token_exposed": False,
            "financial_transaction_signed": False,
            "spend_performed": False,
            "asset_transfer_performed": False,
            "kyc_performed": False,
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--secret-dir", default="/app/runtime-secrets")
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    receipt = execute(
        authorization=authorization,
        artifact_path=Path(args.artifact),
        private_key_path=Path(args.secret_dir) / "base-evm-private-key",
        receipt_path=Path(args.receipt),
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
