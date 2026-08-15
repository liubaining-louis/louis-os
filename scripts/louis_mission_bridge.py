#!/usr/bin/env python3
"""Generic ChatGPT <-> Louis OS mission escalation queue.

This bridge never performs an external action. It only moves a sanitized mission
question from the VM to the operator/tutor channel and stores the returned answer
for a worker to inspect, test and act on under the normal Louis OS guardrails.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.getenv("LOUIS_MISSION_BRIDGE_DIR", "/var/lib/louis-os/state/mission_bridge"))
STATE_PATH = STATE_DIR / "requests.json"
MAX_PUBLIC_TEXT = int(os.getenv("LOUIS_MISSION_BRIDGE_MAX_PUBLIC_TEXT", "8000"))

SENSITIVE_KEY = re.compile(
    r"(?i)(api[_ -]?key|authorization|bearer|access[_ -]?token|refresh[_ -]?token|token|cookie|password|passwd|secret|private[_ -]?key|session[_ -]?(?:id|token|cookie)?)"
)
SECRET_PATTERNS = [
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"requests": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"requests": {}}


def save(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(STATE_PATH)


def redact_text(value: str) -> str:
    text = value
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    lines: list[str] = []
    for line in text.splitlines():
        if SENSITIVE_KEY.search(line) and any(sep in line for sep in (":", "=", " ")):
            # Preserve the fact that credentials/auth were involved without publishing values.
            key = line.split(":", 1)[0].split("=", 1)[0].strip()[:80]
            lines.append(f"{key}: [REDACTED_SENSITIVE_LINE]")
        else:
            lines.append(line)
    text = "\n".join(lines)
    if len(text) > MAX_PUBLIC_TEXT:
        text = text[:MAX_PUBLIC_TEXT] + "\n[TRUNCATED]"
    return text


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if SENSITIVE_KEY.search(str(key)):
                out[str(key)] = "[REDACTED_SENSITIVE_FIELD]"
            else:
                out[str(key)] = sanitize(item)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value[:100]]
    if isinstance(value, str):
        return redact_text(value)
    return value


def decode_json_b64(value: str | None, default: Any) -> Any:
    if not value:
        return default
    raw = base64.b64decode(value).decode("utf-8")
    return json.loads(raw)


def request(args: argparse.Namespace) -> dict[str, Any]:
    data = load()
    request_id = args.request_id or f"mbr_{uuid.uuid4().hex[:16]}"
    if request_id in data.setdefault("requests", {}):
        return {"status": "exists", "request_id": request_id}

    context = decode_json_b64(args.context_b64, {})
    record = {
        "request_id": request_id,
        "mission_id": args.mission_id,
        "source": args.source,
        "objective": args.objective,
        "blocker": args.blocker,
        "requested_output": args.requested_output,
        "context_private": context,
        "context_public": sanitize(context),
        "risk": args.risk,
        "status": "pending_publish",
        "created_at": now(),
        "updated_at": now(),
        "published_comment_id": None,
        "response": None,
        "response_at": None,
        "consumed_at": None,
    }
    data["requests"][request_id] = record
    save(data)
    return {"status": "queued", "request_id": request_id}


def public_envelope(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": record.get("request_id"),
        "mission_id": record.get("mission_id"),
        "source": record.get("source"),
        "objective": redact_text(str(record.get("objective") or "")),
        "blocker": redact_text(str(record.get("blocker") or "")),
        "requested_output": redact_text(str(record.get("requested_output") or "")),
        "context": record.get("context_public") or {},
        "risk": record.get("risk") or "low",
        "created_at": record.get("created_at"),
    }


def pending(_: argparse.Namespace) -> dict[str, Any]:
    data = load()
    items = [r for r in data.get("requests", {}).values() if r.get("status") == "pending_publish"]
    items.sort(key=lambda r: r.get("created_at") or "")
    if not items:
        return {"status": "empty"}
    return {"status": "pending", "request": public_envelope(items[0])}


def mark_published(args: argparse.Namespace) -> dict[str, Any]:
    data = load()
    record = data.get("requests", {}).get(args.request_id)
    if not record:
        raise SystemExit("request_not_found")
    if record.get("status") not in {"pending_publish", "published"}:
        return {"status": record.get("status"), "request_id": args.request_id}
    record["status"] = "published"
    record["published_comment_id"] = args.comment_id
    record["updated_at"] = now()
    save(data)
    return {"status": "published", "request_id": args.request_id}


def answer(args: argparse.Namespace) -> dict[str, Any]:
    data = load()
    record = data.get("requests", {}).get(args.request_id)
    if not record:
        raise SystemExit("request_not_found")
    if record.get("status") == "consumed":
        return {"status": "already_consumed", "request_id": args.request_id}
    response = decode_json_b64(args.response_b64, None)
    # Responses are stored privately on the VM. The bridge still does not execute them.
    record["response"] = response
    record["response_at"] = now()
    record["status"] = "answered"
    record["updated_at"] = now()
    save(data)
    return {"status": "answered", "request_id": args.request_id}


def consume(args: argparse.Namespace) -> dict[str, Any]:
    data = load()
    record = data.get("requests", {}).get(args.request_id)
    if not record:
        raise SystemExit("request_not_found")
    if record.get("status") not in {"answered", "consumed"}:
        return {"status": record.get("status"), "request_id": args.request_id, "response": None}
    if record.get("status") == "answered":
        record["status"] = "consumed"
        record["consumed_at"] = now()
        record["updated_at"] = now()
        save(data)
    return {"status": "consumed", "request_id": args.request_id, "response": record.get("response")}


def status(args: argparse.Namespace) -> dict[str, Any]:
    data = load()
    if args.request_id:
        record = data.get("requests", {}).get(args.request_id)
        if not record:
            return {"status": "not_found", "request_id": args.request_id}
        return {
            "status": record.get("status"),
            "request_id": args.request_id,
            "mission_id": record.get("mission_id"),
            "source": record.get("source"),
            "has_response": record.get("response") is not None,
            "created_at": record.get("created_at"),
            "response_at": record.get("response_at"),
            "consumed_at": record.get("consumed_at"),
        }
    counts: dict[str, int] = {}
    for record in data.get("requests", {}).values():
        key = str(record.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {"status": "ok", "counts": counts, "total": sum(counts.values())}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("request")
    p.add_argument("--request-id")
    p.add_argument("--mission-id", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--blocker", required=True)
    p.add_argument("--requested-output", default="Provide the safest next step and a concrete solution or patch.")
    p.add_argument("--context-b64")
    p.add_argument("--risk", choices=["low", "medium", "high"], default="low")

    sub.add_parser("pending")

    p = sub.add_parser("mark-published")
    p.add_argument("--request-id", required=True)
    p.add_argument("--comment-id", required=True)

    p = sub.add_parser("answer")
    p.add_argument("--request-id", required=True)
    p.add_argument("--response-b64", required=True)

    p = sub.add_parser("consume")
    p.add_argument("--request-id", required=True)

    p = sub.add_parser("status")
    p.add_argument("--request-id")

    args = parser.parse_args()
    func = {
        "request": request,
        "pending": pending,
        "mark-published": mark_published,
        "answer": answer,
        "consume": consume,
        "status": status,
    }[args.cmd]
    print(json.dumps(func(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
