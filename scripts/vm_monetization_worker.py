#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from atlas.vm_command_bus import process_pending_vm_commands

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HEARTBEAT = RESULTS / "vm_worker_heartbeat.json"
LOCK = ROOT / ".vm_monetization_worker.lock"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
LIVE_COLLECTION = os.getenv("LOUIS_LIVE_STATE_COLLECTION", "louis_live")
LIVE_DOCUMENT = os.getenv("LOUIS_LIVE_STATE_DOCUMENT", "current")

DEFAULT_COMMANDS = [
    [sys.executable, "scripts/universal_market_cycle.py"],
    [sys.executable, "scripts/cash_first_recovery_cycle.py"],
    [sys.executable, "scripts/multi_model_monetization_cycle.py"],
    [sys.executable, "scripts/sync_operational_state_to_firestore.py"],
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def monetization_projection() -> dict[str, Any]:
    money = read_json(RESULTS / "monetization.json")
    apprenticeship = read_json(RESULTS / "paid_mission_apprenticeship.json")
    coaching = apprenticeship.get("coaching") if isinstance(apprenticeship.get("coaching"), dict) else {}
    mission = apprenticeship.get("mission") if apprenticeship.get("selected") else None
    return {
        "execute_now": int(money.get("universal_market_executable_now", money.get("execute_now", 0)) or 0),
        "prepare_then_gate": int(money.get("universal_market_prepare_then_gate", money.get("prepare_then_gate", 0)) or 0),
        "external_submissions_verified": int(
            money.get("external_submissions_verified", money.get("external_actions_submitted", 0)) or 0
        ),
        "revenue_verified_eur": float(
            money.get("revenue_confirmed_eur", money.get("revenue_verified_eur", 0.0)) or 0.0
        ),
        "current_mission": mission,
        "mission_stage": coaching.get("stage", "none"),
        "next_action": coaching.get("next_action") or money.get("next_action"),
        "primary_blocker": money.get("primary_blocker"),
        "monetization_updated_at": money.get("updated_at", money.get("generated_at")),
        "multi_model_review_status": money.get("multi_model_review_status"),
        "multi_model_selected_candidate": money.get("multi_model_selected_candidate"),
        "multi_model_recommendation": money.get("multi_model_recommendation"),
        "multi_model_critic_pass": money.get("multi_model_critic_pass"),
        "multi_model_policy": money.get("multi_model_policy"),
    }


def publish_firestore(payload: dict[str, Any]) -> str | None:
    if os.getenv("LOUIS_LIVE_STATE_FIRESTORE", "1").lower() in {"0", "false", "no", "off"}:
        return "disabled"
    try:
        from google.cloud import firestore

        db = firestore.Client(project=PROJECT_ID)
        db.collection(LIVE_COLLECTION).document(LIVE_DOCUMENT).set(payload)
        db.collection("louis_runtime").document("current").set(
            {
                "worker_status": payload.get("status"),
                "worker_verified": True,
                "last_cycle_at": payload.get("updated_at"),
                "last_cycle_status": payload.get("phase"),
                "execution_status": payload.get("phase"),
                "current_activity": payload.get("current_command") or payload.get("next_action"),
                "next_action": payload.get("next_action"),
                "external_actions_submitted": payload.get("external_submissions_verified", 0),
                "revenue_confirmed_eur": payload.get("revenue_verified_eur", 0.0),
                "live_worker_status": payload.get("status"),
                "live_worker_phase": payload.get("phase"),
                "live_worker_cycle": payload.get("cycle"),
                "live_worker_current_command": payload.get("current_command"),
                "live_worker_updated_at": payload.get("updated_at"),
                "live_worker_heartbeat_seconds": payload.get("heartbeat_interval_seconds"),
                "execute_now": payload.get("execute_now", 0),
                "prepare_then_gate": payload.get("prepare_then_gate", 0),
                "primary_blocker": payload.get("primary_blocker"),
                "multi_model_review_status": payload.get("multi_model_review_status"),
                "multi_model_selected_candidate": payload.get("multi_model_selected_candidate"),
                "multi_model_recommendation": payload.get("multi_model_recommendation"),
                "multi_model_critic_pass": payload.get("multi_model_critic_pass"),
                "multi_model_policy": payload.get("multi_model_policy"),
                "vm_command_bus_last_processed": payload.get("vm_command_bus_last_processed"),
                "vm_command_bus_error": payload.get("vm_command_bus_error"),
            },
            merge=True,
        )
        return None
    except Exception as exc:
        return type(exc).__name__


def write_heartbeat(**extra: object) -> dict[str, Any]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "2.2",
        "worker": "gcp_vm_monetization_worker",
        "project": PROJECT_ID,
        "updated_at": now_iso(),
        "pid": os.getpid(),
        **monetization_projection(),
        **extra,
    }
    HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    error = publish_firestore(payload)
    if error and error != "disabled":
        payload["firestore_publish_error"] = error
        HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    elif error == "disabled":
        payload["firestore_publish_status"] = "disabled"
    else:
        payload["firestore_publish_status"] = "ok"
    return payload


def process_vm_queue() -> tuple[list[dict[str, Any]], str | None]:
    try:
        return process_pending_vm_commands(ROOT), None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def run_command(command: list[str], *, cycle: int, heartbeat_interval: int, steps_completed: int) -> dict[str, object]:
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=heartbeat_interval)
            break
        except subprocess.TimeoutExpired:
            processed, queue_error = process_vm_queue()
            write_heartbeat(
                status="running",
                phase="executing_command",
                cycle=cycle,
                current_command=" ".join(command),
                command_started_at_monotonic=round(started, 3),
                steps_completed=steps_completed,
                heartbeat_interval_seconds=heartbeat_interval,
                vm_command_bus_last_processed=processed,
                vm_command_bus_error=queue_error,
            )
    return {
        "command": command,
        "returncode": proc.returncode,
        "duration_s": round(time.monotonic() - started, 2),
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
    }


def idle_with_heartbeat(*, seconds: int, cycle: int, heartbeat_interval: int, last_ok: bool, steps: list[dict[str, object]]) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        processed, queue_error = process_vm_queue()
        write_heartbeat(
            status="healthy" if last_ok else "degraded",
            phase="idle_between_cycles",
            cycle=cycle,
            current_command=None,
            next_cycle_in_seconds=max(0, round(remaining)),
            heartbeat_interval_seconds=heartbeat_interval,
            steps=steps,
            vm_command_bus_last_processed=processed,
            vm_command_bus_error=queue_error,
        )
        time.sleep(min(heartbeat_interval, remaining))


def acquire_lock() -> int:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError:
        raise SystemExit("another VM monetization worker is already running")


def main() -> int:
    interval = max(60, int(os.getenv("LOUIS_VM_INTERVAL_SECONDS", "300")))
    heartbeat_interval = max(5, int(os.getenv("LOUIS_VM_HEARTBEAT_SECONDS", "10")))
    once = os.getenv("LOUIS_VM_RUN_ONCE", "0") == "1"
    lock_fd = acquire_lock()
    cycle = 0
    try:
        while True:
            cycle += 1
            started_at = now_iso()
            processed, queue_error = process_vm_queue()
            write_heartbeat(
                status="running", phase="cycle_start", cycle=cycle, started_at=started_at,
                current_command=None, heartbeat_interval_seconds=heartbeat_interval,
                vm_command_bus_last_processed=processed, vm_command_bus_error=queue_error,
            )
            steps: list[dict[str, object]] = []
            ok = True
            for command in DEFAULT_COMMANDS:
                if not (ROOT / command[1]).exists():
                    steps.append({"command": command, "skipped": True, "reason": "script_missing"})
                    continue
                write_heartbeat(
                    status="running", phase="command_start", cycle=cycle, started_at=started_at,
                    current_command=" ".join(command), steps_completed=len(steps), heartbeat_interval_seconds=heartbeat_interval,
                )
                result = run_command(command, cycle=cycle, heartbeat_interval=heartbeat_interval, steps_completed=len(steps))
                steps.append(result)
                if result["returncode"] != 0:
                    ok = False
                    break
            processed, queue_error = process_vm_queue()
            write_heartbeat(
                status="healthy" if ok else "degraded", phase="cycle_complete", cycle=cycle,
                started_at=started_at, finished_at=now_iso(), interval_seconds=interval,
                heartbeat_interval_seconds=heartbeat_interval, current_command=None, steps=steps,
                vm_command_bus_last_processed=processed, vm_command_bus_error=queue_error,
            )
            if once:
                return 0 if ok else 1
            idle_with_heartbeat(seconds=interval, cycle=cycle, heartbeat_interval=heartbeat_interval, last_ok=ok, steps=steps)
    finally:
        try:
            os.close(lock_fd)
        finally:
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
