from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .report import generate_report
from .runner import ROOT, run_all


class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "LouisOS/0.1"

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send_json({
                "service": "louis-os-atlas",
                "version": "0.1.0",
                "status": "ok",
            })
            return

        if path == "/results":
            summary_path = ROOT / "results" / "summary.json"
            if not summary_path.exists():
                self._send_json(
                    {"error": "No benchmark result available. Run POST /run first."},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self._send_json(json.loads(summary_path.read_text(encoding="utf-8")))
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/run":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            summary = run_all(clear=True)
            generate_report()
            self._send_json({"status": "completed", "summary": summary})
        except Exception as exc:  # pragma: no cover - defensive production boundary
            self._send_json(
                {"status": "failed", "error": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[atlas-http] {self.address_string()} - {fmt % args}")


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AtlasHandler)
    print(f"Louis OS ATLAS listening on 0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
