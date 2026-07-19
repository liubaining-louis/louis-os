"""Secure, allowlisted Google Cloud control bridge for Louis OS.

This service intentionally exposes only a small set of operations. It does not
execute arbitrary shell commands and it requires a shared bearer token stored in
Secret Manager and injected as LOUIS_BRIDGE_KEY.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
DEFAULT_ZONE = os.getenv("LOUIS_DEFAULT_ZONE", "europe-west1-b")
BRIDGE_KEY = os.getenv("LOUIS_BRIDGE_KEY", "")
PORT = int(os.getenv("PORT", "8080"))


def _metadata_token() -> str:
    request = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)["access_token"]


def _google_request(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {_metadata_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            detail = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, detail


def _json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not BRIDGE_KEY:
        return False
    auth = handler.headers.get("Authorization", "")
    return auth == f"Bearer {BRIDGE_KEY}"


class Handler(BaseHTTPRequestHandler):
    server_version = "LouisGCloudBridge/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            _json(self, 200, {"status": "ok", "project": PROJECT_ID})
            return
        if not _authorized(self):
            _json(self, 401, {"error": "unauthorized"})
            return

        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/v1/instances":
            zone = query.get("zone", [DEFAULT_ZONE])[0]
            url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT_ID}/zones/{zone}/instances"
            status, result = _google_request("GET", url)
            if status == 200:
                items = [
                    {
                        "name": item.get("name"),
                        "status": item.get("status"),
                        "machineType": item.get("machineType", "").rsplit("/", 1)[-1],
                        "internalIp": (item.get("networkInterfaces") or [{}])[0].get("networkIP"),
                    }
                    for item in result.get("items", [])
                ]
                result = {"project": PROJECT_ID, "zone": zone, "instances": items}
            _json(self, status, result)
            return

        if parsed.path == "/v1/project":
            _json(self, 200, {"project": PROJECT_ID, "defaultZone": DEFAULT_ZONE, "allowedActions": ["list_instances", "start_instance", "stop_instance", "reset_instance"]})
            return

        _json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not _authorized(self):
            _json(self, 401, {"error": "unauthorized"})
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 4 or parts[:2] != ["v1", "instances"] or parts[3] not in {"start", "stop", "reset"}:
            _json(self, 404, {"error": "not_found"})
            return

        instance = parts[2]
        if not instance.replace("-", "").isalnum():
            _json(self, 400, {"error": "invalid_instance"})
            return

        query = urllib.parse.parse_qs(parsed.query)
        zone = query.get("zone", [DEFAULT_ZONE])[0]
        action = parts[3]
        url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT_ID}/zones/{zone}/instances/{instance}/{action}"
        status, result = _google_request("POST", url, {})
        _json(self, status, {"action": action, "instance": instance, "zone": zone, "operation": result})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Louis GCloud bridge listening on :{PORT} for project {PROJECT_ID}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
