from __future__ import annotations

import hashlib
import hmac
import os
import time
from http.cookies import SimpleCookie

_COOKIE_NAME = "louis_session"
_DEFAULT_TTL_SECONDS = 12 * 60 * 60


def _secret() -> str:
    return os.environ.get("LOUIS_OS_API_KEY", "").strip()


def api_key_matches(supplied: str) -> bool:
    """Validate an explicitly supplied API key without issuing credentials."""
    expected = _secret()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _ttl_seconds() -> int:
    try:
        value = int(os.environ.get("WEB_SESSION_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS)))
    except ValueError:
        value = _DEFAULT_TTL_SECONDS
    return min(max(value, 300), 7 * 24 * 60 * 60)


def create_session_token(now: int | None = None) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError("LOUIS_OS_API_KEY is not configured")
    expires_at = int(now if now is not None else time.time()) + _ttl_seconds()
    payload = str(expires_at)
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def validate_session_token(token: str, now: int | None = None) -> bool:
    secret = _secret()
    if not secret or not token or "." not in token:
        return False
    expires_text, supplied_signature = token.split(".", 1)
    try:
        expires_at = int(expires_text)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if expires_at < current:
        return False
    expected_signature = hmac.new(
        secret.encode("utf-8"), expires_text.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, supplied_signature)


def token_from_cookie_header(cookie_header: str) -> str:
    if not cookie_header:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return ""
    morsel = cookie.get(_COOKIE_NAME)
    return morsel.value if morsel else ""


def build_set_cookie_header(now: int | None = None) -> str:
    token = create_session_token(now=now)
    return (
        f"{_COOKIE_NAME}={token}; Path=/; Max-Age={_ttl_seconds()}; "
        "HttpOnly; Secure; SameSite=Strict"
    )
