#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "https://api.moltjobs.io/v1"
PACK_ID = "pack_01_general"
MODE = "CLOSED_BOOK"
STATE_DIR = Path("/var/lib/louis-os/state")
STATE_PATH = STATE_DIR / "moltjobs_chatgpt_exam_relay.json"
KEY_PATH = Path("/var/lib/louis-os/secrets/moltjobs_api_key")


def _key() -> str:
    value = KEY_PATH.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("moltjobs_api_key_missing")
    return value


def _request(method: str, path: str, body: Any | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"moltjobs_http_{exc.code}:{raw[:500]}") from exc
    parsed = json.loads(raw) if raw else None
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def _load() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(STATE_PATH)


def _public_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict) or not item.get("itemId"):
        return {"status": "exhausted", "index": index}
    return {
        "status": "question",
        "index": index,
        "itemId": item.get("itemId"),
        "type": item.get("type"),
        "prompt": item.get("prompt"),
        "options": item.get("options"),
    }


def _finalize_state(state: dict[str, Any]) -> dict[str, Any]:
    quiz_id = state.get("quizId")
    if not quiz_id:
        raise RuntimeError("no_relay_session")
    if state.get("finished") and state.get("report") is not None:
        return {"status": "finished", "answered": int(state.get("answered", 0)), "report": state.get("report")}
    _request("POST", f"/evals/{quiz_id}/finalize", {})
    report = _request("GET", f"/evals/{quiz_id}/report")
    state.update({"currentItemId": None, "finished": True, "report": report})
    _save(state)
    return {"status": "finished", "answered": int(state.get("answered", 0)), "report": report}


def start() -> dict[str, Any]:
    session = _request("POST", "/evals", {"packId": PACK_ID, "mode": MODE})
    quiz_id = session.get("quizId") if isinstance(session, dict) else None
    if not quiz_id:
        raise RuntimeError("quiz_id_missing")
    item = _request("GET", f"/evals/{quiz_id}/next")
    state = {
        "quizId": quiz_id,
        "packId": PACK_ID,
        "mode": MODE,
        "answered": 0,
        "currentItemId": item.get("itemId") if isinstance(item, dict) else None,
        "finished": False,
    }
    _save(state)
    if not isinstance(item, dict) or not item.get("itemId"):
        return _finalize_state(state)
    return _public_item(item, 1)


def heartbeat() -> dict[str, Any]:
    state = _load()
    quiz_id = state.get("quizId")
    if not quiz_id or state.get("finished"):
        raise RuntimeError("no_active_relay_session")
    _request("POST", f"/evals/{quiz_id}/heartbeat", {})
    return {"status": "heartbeat_ok", "answered": int(state.get("answered", 0))}


def answer(answer_b64: str) -> dict[str, Any]:
    state = _load()
    quiz_id = state.get("quizId")
    item_id = state.get("currentItemId")
    if not quiz_id or not item_id or state.get("finished"):
        raise RuntimeError("no_active_relay_session")

    raw = base64.b64decode(answer_b64).decode("utf-8").strip()
    try:
        parsed = json.loads(raw)
        value = parsed.get("answer") if isinstance(parsed, dict) and "answer" in parsed else parsed
    except json.JSONDecodeError:
        value = raw

    _request(
        "POST",
        f"/evals/{quiz_id}/items/{item_id}/answer",
        {"answer": value, "telemetry": {"solver": "chatgpt_relay"}},
    )
    answered = int(state.get("answered", 0)) + 1
    state["answered"] = answered
    if answered % 3 == 0:
        try:
            _request("POST", f"/evals/{quiz_id}/heartbeat", {})
        except Exception:
            pass

    item = _request("GET", f"/evals/{quiz_id}/next")
    if not isinstance(item, dict) or not item.get("itemId"):
        state["currentItemId"] = None
        _save(state)
        return _finalize_state(state)

    state.update({"currentItemId": item.get("itemId"), "finished": False})
    _save(state)
    return _public_item(item, answered + 1)


def finalize_current() -> dict[str, Any]:
    return _finalize_state(_load())


def status() -> dict[str, Any]:
    state = _load()
    return {
        "status": "finished" if state.get("finished") else "active" if state.get("quizId") else "idle",
        "answered": state.get("answered", 0),
        "finished": bool(state.get("finished")),
        "report": state.get("report") if state.get("finished") else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    a = sub.add_parser("answer")
    a.add_argument("--answer-b64", required=True)
    sub.add_parser("heartbeat")
    sub.add_parser("finalize")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "start":
        result = start()
    elif args.cmd == "answer":
        result = answer(args.answer_b64)
    elif args.cmd == "heartbeat":
        result = heartbeat()
    elif args.cmd == "finalize":
        result = finalize_current()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
