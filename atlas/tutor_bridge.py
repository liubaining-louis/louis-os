from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.getenv("LOUIS_TUTOR_MODEL", "gpt-5.2")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_tutor_snapshot(root: Path) -> dict[str, Any]:
    results = root / "results"
    heartbeat = _safe_json(results / "vm_worker_heartbeat.json")
    browser = _safe_json(results / "browser_runtime.json")
    money = _safe_json(results / "monetization.json")
    strike = _safe_json(results / "revenue-strike-v3" / "selected.json")

    return {
        "observed_at": _now(),
        "worker": heartbeat.get("worker"),
        "status": heartbeat.get("status"),
        "phase": heartbeat.get("phase"),
        "cycle": heartbeat.get("cycle"),
        "current_command": heartbeat.get("current_command"),
        "next_action": heartbeat.get("next_action"),
        "primary_blocker": heartbeat.get("primary_blocker"),
        "productive_utilization_pct": heartbeat.get("productive_utilization_pct"),
        "active_work_seconds": heartbeat.get("active_work_seconds"),
        "actions_completed_in_cycle": heartbeat.get("actions_completed_in_cycle"),
        "execute_now": heartbeat.get("execute_now"),
        "prepare_then_gate": heartbeat.get("prepare_then_gate"),
        "external_submissions_verified": heartbeat.get("external_submissions_verified"),
        "revenue_verified_eur": heartbeat.get("revenue_verified_eur"),
        "autonomy_action": heartbeat.get("autonomy_action"),
        "autonomy_status": heartbeat.get("autonomy_status"),
        "autonomy_score": heartbeat.get("autonomy_score"),
        "browser_status": browser.get("status"),
        "browser_final_url": browser.get("final_url"),
        "browser_http_status": browser.get("http_status"),
        "browser_reason": browser.get("reason"),
        "monetization_status": money.get("status"),
        "monetization_next_action": money.get("next_action"),
        "selected_revenue_candidate": {
            "title": strike.get("title"),
            "rewardAmount": strike.get("rewardAmount"),
            "token": strike.get("token"),
            "deadline": strike.get("deadline"),
            "agentAccess": strike.get("agentAccess"),
        } if strike else None,
    }


def _extract_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "output_text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError("openai_response_without_output_text")
    return text


def ask_openai_tutor(snapshot: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "blocked",
            "provider": "openai",
            "reason": "OPENAI_API_KEY_missing",
            "generated_at": _now(),
        }

    instructions = (
        "You are the senior tutor and supervisor of Louis OS. Review only the supplied runtime snapshot. "
        "Prioritize real paid outcomes over activity. Distinguish facts from hypotheses. Do not invent completed actions, "
        "submissions, acceptance, or revenue. Never request or expose secrets. Return concise JSON with keys: "
        "assessment, priority, next_action, stop_or_pivot_rule, human_gate, confidence. "
        "Do not authorize spending, wallet signing, KYC, legal commitments, or unsafe actions."
    )
    payload = json.dumps({
        "model": DEFAULT_MODEL,
        "instructions": instructions,
        "input": json.dumps(snapshot, ensure_ascii=False),
        "store": False,
    }).encode("utf-8")
    request = Request(
        OPENAI_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LouisOS-TutorBridge/1.0",
        },
    )
    timeout = max(10, min(int(os.getenv("LOUIS_TUTOR_TIMEOUT_SECONDS", "75")), 180))
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "status": "failed",
            "provider": "openai",
            "reason": f"HTTP_{exc.code}",
            "detail": details,
            "generated_at": _now(),
        }
    except URLError as exc:
        return {
            "status": "failed",
            "provider": "openai",
            "reason": f"connection_error:{exc.reason}",
            "generated_at": _now(),
        }

    text = _extract_text(data)
    try:
        advice = json.loads(text)
    except json.JSONDecodeError:
        advice = {"assessment": text, "priority": None, "next_action": None}
    return {
        "status": "completed",
        "provider": "openai",
        "model": data.get("model", DEFAULT_MODEL),
        "response_id": data.get("id"),
        "generated_at": _now(),
        "snapshot": snapshot,
        "advice": advice,
    }


def publish_tutor_state(root: Path, payload: dict[str, Any]) -> None:
    results = root / "results"
    results.mkdir(parents=True, exist_ok=True)
    path = results / "tutor_bridge.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    try:
        from google.cloud import firestore
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
        db = firestore.Client(project=project)
        db.collection("louis_tutor").document("current").set(payload, merge=True)
        advice = payload.get("advice") if isinstance(payload.get("advice"), dict) else {}
        db.collection("louis_live").document("current").set({
            "tutor_status": payload.get("status"),
            "tutor_provider": payload.get("provider"),
            "tutor_model": payload.get("model"),
            "tutor_updated_at": payload.get("generated_at"),
            "tutor_priority": advice.get("priority"),
            "tutor_next_action": advice.get("next_action"),
            "tutor_human_gate": advice.get("human_gate"),
            "tutor_confidence": advice.get("confidence"),
        }, merge=True)
    except Exception as exc:
        payload["firestore_publish_error"] = type(exc).__name__
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def run_tutor_cycle(root: Path) -> dict[str, Any]:
    snapshot = build_tutor_snapshot(root)
    payload = ask_openai_tutor(snapshot)
    publish_tutor_state(root, payload)
    return payload
