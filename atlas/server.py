from __future__ import annotations

import hmac
import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .core import build_plan, validate_plan
from .memory import create_memory, get_memory, list_memories, retrieve_memories
from .missions import get_mission, list_missions, run_mission
from .providers import complete
from .report import generate_report
from .runner import ROOT, run_all


class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "LouisOS/0.6"

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = os.environ.get("LOUIS_OS_API_KEY", "")
        supplied = self.headers.get("X-Louis-Key", "")
        return bool(expected) and hmac.compare_digest(expected, supplied)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            raise ValueError("Invalid request body size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    @staticmethod
    def _parse_limit(params: dict[str, list[str]], default: int = 20) -> int:
        try:
            return min(max(int(params.get("limit", [str(default)])[0]), 1), 100)
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/health"}:
            self._send_json({
                "service": "louis-os-atlas",
                "version": "0.6.0",
                "status": "ok",
                "llm_configured": bool(os.environ.get("LLM_API_KEY")),
                "mission_store": os.environ.get("MISSION_STORE", "local"),
                "memory_store": os.environ.get("MEMORY_STORE", "local"),
                "core": "planning-and-memory-enabled",
            })
            return

        if not self._require_auth():
            return

        try:
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

            if path == "/missions":
                params = parse_qs(parsed.query)
                limit = self._parse_limit(params)
                self._send_json({"missions": list_missions(limit=limit), "limit": limit})
                return

            if path.startswith("/missions/"):
                mission_id = path.removeprefix("/missions/").strip()
                mission = get_mission(mission_id)
                if mission is None:
                    self._send_json({"error": "Mission not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(mission)
                return

            if path == "/memories":
                params = parse_qs(parsed.query)
                limit = self._parse_limit(params)
                query = params.get("query", [""])[0].strip()
                domain = params.get("domain", [""])[0].strip() or None
                memories = (
                    retrieve_memories(query=query, domain=domain, limit=limit)
                    if query
                    else list_memories(limit=limit)
                )
                self._send_json({"memories": memories, "limit": limit, "query": query, "domain": domain})
                return

            if path.startswith("/memories/"):
                memory_id = path.removeprefix("/memories/").strip()
                memory = get_memory(memory_id)
                if memory is None:
                    self._send_json({"error": "Memory not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(memory)
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._require_auth():
            return

        try:
            if path == "/run":
                summary = run_all(clear=True)
                generate_report()
                self._send_json({"status": "completed", "summary": summary})
                return

            if path == "/plan":
                payload = self._read_json()
                objective = str(payload.get("objective", "")).strip()
                context = payload.get("context", {})
                if not isinstance(context, dict):
                    self._send_json({"error": "context must be an object"}, HTTPStatus.BAD_REQUEST)
                    return
                plan = build_plan(objective, context)
                valid, errors = validate_plan(plan)
                self._send_json({
                    "status": "planned" if valid else "rejected",
                    "plan": plan.to_dict(),
                    "validation": {"valid": valid, "errors": errors},
                }, HTTPStatus.CREATED if valid else HTTPStatus.UNPROCESSABLE_ENTITY)
                return

            if path == "/ask":
                payload = self._read_json()
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    self._send_json({"error": "prompt is required"}, HTTPStatus.BAD_REQUEST)
                    return
                result = complete(prompt)
                self._send_json({
                    "status": "completed",
                    "provider": result.provider,
                    "model": result.model,
                    "answer": result.text,
                })
                return

            if path == "/missions":
                payload = self._read_json()
                mission_type = str(payload.get("type", "")).strip()
                objective = str(payload.get("objective", "")).strip()
                context = payload.get("context", {})
                if not mission_type or not objective:
                    self._send_json(
                        {"error": "type and objective are required"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                if not isinstance(context, dict):
                    self._send_json({"error": "context must be an object"}, HTTPStatus.BAD_REQUEST)
                    return
                record = run_mission(mission_type, objective, context)
                self._send_json(asdict(record), HTTPStatus.CREATED)
                return

            if path == "/memories":
                payload = self._read_json()
                tags = payload.get("tags", [])
                if not isinstance(tags, list):
                    self._send_json({"error": "tags must be an array"}, HTTPStatus.BAD_REQUEST)
                    return
                record = create_memory(
                    memory_type=str(payload.get("type", "")).strip(),
                    domain=str(payload.get("domain", "")).strip(),
                    content=str(payload.get("content", "")).strip(),
                    confidence=float(payload.get("confidence", 0.8)),
                    tags=tags,
                    source=str(payload.get("source", "user")).strip() or "user",
                )
                self._send_json(record.to_dict(), HTTPStatus.CREATED)
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - production boundary
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
