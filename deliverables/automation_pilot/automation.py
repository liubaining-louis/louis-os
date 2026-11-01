"""Offline sales demonstration: one webhook and a loopback-only mock API.

No LLM, production destination, credentials, persistence, retries or deployment.
"""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler
import json
import re
import socket
from urllib.parse import urlsplit

MAX_BYTES = 16_384
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def failure(code: str) -> dict:
    return {"ok": False, "error": {"code": code}, "automatic_retry": False}


def process(body: bytes, endpoint: str, timeout: float = 1.0) -> tuple[int, dict]:
    if len(body) > MAX_BYTES:
        return 413, failure("payload_too_large")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError):
        return 400, failure("invalid_json")
    if not isinstance(payload, dict) or set(payload) != {"request_id", "category", "message"}:
        return 400, failure("invalid_schema")
    if (not isinstance(payload["request_id"], str)
            or not IDENTIFIER.fullmatch(payload["request_id"])
            or payload["category"] not in ("sales", "support")
            or not isinstance(payload["message"], str)
            or not 1 <= len(payload["message"].strip()) <= 500):
        return 400, failure("invalid_fields")
    try:
        url = urlsplit(endpoint)
        port = url.port
    except ValueError:
        return 400, failure("demo_endpoint_not_allowed")
    # This demonstrator cannot be pointed at a customer or paid provider.
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or url.username
            or url.password or url.query or url.fragment or url.path != "/mock"):
        return 400, failure("demo_endpoint_not_allowed")
    try:
        if port is None:
            return 400, failure("demo_endpoint_not_allowed")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            connection.request("POST", "/mock", json.dumps(payload).encode(),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                return 502, failure("upstream_http_error")
            raw = response.read(MAX_BYTES + 1)
        finally:
            connection.close()
    except (TimeoutError, socket.timeout):
        return 504, failure("upstream_timeout")
    except (OSError, http.client.HTTPException, ValueError):
        return 502, failure("upstream_connection_error")
    if len(raw) > MAX_BYTES:
        return 502, failure("upstream_response_too_large")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return 502, failure("upstream_invalid_json")
    if (not isinstance(result, dict) or result.get("status") != "received"
            or not isinstance(result.get("ticket_id"), str)
            or not IDENTIFIER.fullmatch(result["ticket_id"])):
        return 502, failure("upstream_invalid_schema")
    return 200, {"ok": True, "request_id": payload["request_id"],
                 "ticket_id": result["ticket_id"], "status": "received"}


def webhook_handler(endpoint: str):
    class Webhook(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # No payload, credentials or personal data in access logs.

        def do_POST(self):
            if self.path != "/webhook":
                status, result = 404, failure("not_found")
            elif self.headers.get_content_type() != "application/json":
                status, result = 415, failure("json_required")
            else:
                try:
                    size = int(self.headers.get("Content-Length", "-1"))
                except ValueError:
                    size = -1
                if size < 0:
                    status, result = 400, failure("content_length_required")
                elif size > MAX_BYTES:
                    status, result = 413, failure("payload_too_large")
                else:
                    status, result = process(self.rfile.read(size), endpoint)
            encoded = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    return Webhook
