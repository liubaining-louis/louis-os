#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from atlas.browser_executor import run_browser_command

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
INTERVAL = max(60, int(os.getenv("LOUIS_BROWSER_MONITOR_INTERVAL_SECONDS", "300")))
TARGET_URL = os.getenv("LOUIS_BROWSER_MONITOR_URL", "https://app.manic.trade/pm")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish(payload: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "browser_runtime.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT_ID)
        db.collection("louis_browser").document("current").set(payload, merge=True)
        db.collection("louis_runtime").document("current").set(
            {
                "browser_status": payload.get("status"),
                "browser_updated_at": payload.get("updated_at"),
                "browser_final_url": payload.get("final_url"),
                "browser_title": payload.get("title"),
                "browser_reason": payload.get("reason"),
            },
            merge=True,
        )
    except Exception as exc:
        payload["firestore_publish_error"] = f"{type(exc).__name__}: {exc}"
        (RESULTS / "browser_runtime.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def one_cycle() -> dict:
    command_id = "vm-browser-monitor-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        outcome = run_browser_command(
            ROOT,
            command_id=command_id,
            order="browser_snapshot",
            context={"url": TARGET_URL, "timeout_ms": 30000, "purpose": "vm_native_browser_health"},
        )
        result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
        payload = {
            "schema_version": "1.0",
            "worker": "gcp_vm_browser_monitor",
            "command_id": command_id,
            "status": outcome.get("status", "failed"),
            "reason": outcome.get("reason"),
            "updated_at": now_iso(),
            "target_url": TARGET_URL,
            "final_url": result.get("final_url"),
            "title": result.get("title"),
            "http_status": result.get("http_status"),
            "evidence": outcome.get("evidence", []),
            "diagnosis": outcome.get("diagnosis", {}),
        }
    except Exception as exc:
        payload = {
            "schema_version": "1.0",
            "worker": "gcp_vm_browser_monitor",
            "command_id": command_id,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "updated_at": now_iso(),
            "target_url": TARGET_URL,
        }
    publish(payload)
    return payload


def main() -> int:
    run_once = os.getenv("LOUIS_BROWSER_MONITOR_RUN_ONCE", "0") == "1"
    while True:
        payload = one_cycle()
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        if run_once:
            return 0 if payload.get("status") == "completed" else 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
