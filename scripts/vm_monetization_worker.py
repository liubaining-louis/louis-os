#!/usr/bin/env python3
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from atlas.vm_command_bus import process_pending_vm_commands

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HEARTBEAT = RESULTS / "vm_worker_heartbeat.json"
LOCK = ROOT / ".vm_monetization_worker.lock"
AUTONOMY_DECISIONS = RESULTS / "autonomy_decisions.jsonl"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
LIVE_COLLECTION = os.getenv("LOUIS_LIVE_STATE_COLLECTION", "louis_live")
LIVE_DOCUMENT = os.getenv("LOUIS_LIVE_STATE_DOCUMENT", "current")

AUTONOMY_COMMAND = [sys.executable, "scripts/autonomy_cycle.py"]
SYNC_COMMAND = [sys.executable, "scripts/sync_operational_state_to_firestore.py"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}



def _bounded_text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[-limit:] if text else None


def recent_autonomy_failures(
    path: Path = AUTONOMY_DECISIONS,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Return bounded causal evidence for the latest failed autonomy decisions."""
    if limit <= 0:
        return []
    failures: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    item = json.loads(raw_line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(item, Mapping):
                    continue
                outcome = item.get("outcome")
                outcome = outcome if isinstance(outcome, Mapping) else {}
                status = str(item.get("status") or outcome.get("status") or "").lower()
                if status not in {"failed", "error", "timeout"}:
                    continue
                failures.append({
                    "decision_id": item.get("decision_id"),
                    "finished_at": item.get("finished_at"),
                    "action": item.get("action"),
                    "authority": item.get("authority"),
                    "status": status,
                    "command": outcome.get("command"),
                    "returncode": outcome.get("returncode"),
                    "reason": _bounded_text(outcome.get("reason"), 500),
                    "stdout_tail": _bounded_text(outcome.get("stdout_tail")),
                    "stderr_tail": _bounded_text(outcome.get("stderr_tail")),
                })
    except OSError:
        return []
    return list(failures)

def monetization_projection() -> dict[str, Any]:
    money = read_json(RESULTS / "monetization.json")
    apprenticeship = read_json(RESULTS / "paid_mission_apprenticeship.json")
    autonomy = read_json(RESULTS / "autonomy_last_decision.json")
    autonomy_state = read_json(RESULTS / "autonomy_state.json")
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
        "next_action": autonomy.get("action") or coaching.get("next_action") or money.get("next_action"),
        "primary_blocker": money.get("primary_blocker"),
        "monetization_updated_at": money.get("updated_at", money.get("generated_at")),
        "multi_model_review_status": money.get("multi_model_review_status"),
        "multi_model_selected_candidate": money.get("multi_model_selected_candidate"),
        "multi_model_recommendation": money.get("multi_model_recommendation"),
        "multi_model_critic_pass": money.get("multi_model_critic_pass"),
        "multi_model_policy": money.get("multi_model_policy"),
        "autonomy_cycle": autonomy_state.get("cycle"),
        "autonomy_decision_id": autonomy.get("decision_id"),
        "autonomy_action": autonomy.get("action"),
        "autonomy_authority": autonomy.get("authority"),
        "autonomy_score": autonomy.get("score"),
        "autonomy_hypothesis": autonomy.get("hypothesis"),
        "autonomy_measured_delta": autonomy.get("measured_delta"),
        "autonomy_status": autonomy.get("status"),
        "autonomy_recent_failures": recent_autonomy_failures(),
    }


def capacity_snapshot(
    *,
    cycle_started_monotonic: float,
    cycle_budget_seconds: int,
    active_work_seconds: float,
    actions_completed_in_cycle: int,
    unused_capacity_reason: str | None = None,
) -> dict[str, Any]:
    elapsed = max(0.0, time.monotonic() - cycle_started_monotonic)
    remaining = max(0.0, float(cycle_budget_seconds) - elapsed)
    productive_utilization = 100.0 * active_work_seconds / max(elapsed, 0.001)
    return {
        "cycle_budget_seconds": cycle_budget_seconds,
        "cycle_elapsed_seconds": round(elapsed, 2),
        "cycle_remaining_seconds": round(remaining, 2),
        "active_work_seconds": round(active_work_seconds, 2),
        "actions_completed_in_cycle": actions_completed_in_cycle,
        "productive_utilization_pct": round(min(100.0, productive_utilization), 2),
        "budget_consumed_pct": round(min(100.0, 100.0 * elapsed / max(cycle_budget_seconds, 1)), 2),
        "unused_capacity_reason": unused_capacity_reason,
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
                "autonomy_cycle": payload.get("autonomy_cycle"),
                "autonomy_decision_id": payload.get("autonomy_decision_id"),
                "autonomy_action": payload.get("autonomy_action"),
                "autonomy_authority": payload.get("autonomy_authority"),
                "autonomy_score": payload.get("autonomy_score"),
                "autonomy_status": payload.get("autonomy_status"),
                "autonomy_measured_delta": payload.get("autonomy_measured_delta"),
                "cycle_budget_seconds": payload.get("cycle_budget_seconds"),
                "cycle_elapsed_seconds": payload.get("cycle_elapsed_seconds"),
                "cycle_remaining_seconds": payload.get("cycle_remaining_seconds"),
                "active_work_seconds": payload.get("active_work_seconds"),
                "actions_completed_in_cycle": payload.get("actions_completed_in_cycle"),
                "productive_utilization_pct": payload.get("productive_utilization_pct"),
                "budget_consumed_pct": payload.get("budget_consumed_pct"),
                "unused_capacity_reason": payload.get("unused_capacity_reason"),
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
        "schema_version": "3.1",
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


def _stop_process_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()


def run_command(
    command: list[str],
    *,
    cycle: int,
    heartbeat_interval: int,
    steps_completed: int,
    cycle_started_monotonic: float,
    cycle_budget_seconds: int,
    active_work_seconds_before: float,
    actions_completed_in_cycle: int,
    hard_timeout_seconds: float | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout = ""
    stderr = ""
    timed_out = False
    while True:
        elapsed_command = time.monotonic() - started
        if hard_timeout_seconds is not None and elapsed_command >= hard_timeout_seconds:
            timed_out = True
            _stop_process_group(proc)
            stdout, stderr = proc.communicate()
            break
        wait_for = heartbeat_interval
        if hard_timeout_seconds is not None:
            wait_for = max(0.1, min(wait_for, hard_timeout_seconds - elapsed_command))
        try:
            stdout, stderr = proc.communicate(timeout=wait_for)
            break
        except subprocess.TimeoutExpired:
            processed, queue_error = process_vm_queue()
            current_active = active_work_seconds_before + (time.monotonic() - started)
            write_heartbeat(
                status="running",
                phase="executing_autonomous_work",
                cycle=cycle,
                current_command=" ".join(command),
                command_started_at_monotonic=round(started, 3),
                steps_completed=steps_completed,
                heartbeat_interval_seconds=heartbeat_interval,
                vm_command_bus_last_processed=processed,
                vm_command_bus_error=queue_error,
                **capacity_snapshot(
                    cycle_started_monotonic=cycle_started_monotonic,
                    cycle_budget_seconds=cycle_budget_seconds,
                    active_work_seconds=current_active,
                    actions_completed_in_cycle=actions_completed_in_cycle,
                ),
            )
    duration = round(time.monotonic() - started, 2)
    return {
        "command": command,
        "returncode": 124 if timed_out else proc.returncode,
        "timed_out": timed_out,
        "duration_s": duration,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
    }


def acquire_lock() -> int:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError:
        raise SystemExit("another VM monetization worker is already running")


def main() -> int:
    legacy_interval = int(os.getenv("LOUIS_VM_INTERVAL_SECONDS", "300"))
    cycle_budget_seconds = max(30, int(os.getenv("LOUIS_VM_CYCLE_BUDGET_SECONDS", str(legacy_interval))))
    heartbeat_interval = max(5, int(os.getenv("LOUIS_VM_HEARTBEAT_SECONDS", "10")))
    sync_reserve_seconds = max(5, int(os.getenv("LOUIS_VM_SYNC_RESERVE_SECONDS", "20")))
    min_action_window_seconds = max(5, int(os.getenv("LOUIS_VM_MIN_ACTION_WINDOW_SECONDS", "15")))
    max_actions_per_cycle = max(1, int(os.getenv("LOUIS_VM_MAX_ACTIONS_PER_CYCLE", "12")))
    failure_backoff_seconds = max(1, int(os.getenv("LOUIS_VM_FAILURE_BACKOFF_SECONDS", "5")))
    once = os.getenv("LOUIS_VM_RUN_ONCE", "0") == "1"
    lock_fd = acquire_lock()
    cycle = 0
    try:
        while True:
            cycle += 1
            cycle_started_at = now_iso()
            cycle_started_monotonic = time.monotonic()
            active_work_seconds = 0.0
            overhead_seconds = 0.0
            actions_completed_in_cycle = 0
            consecutive_failures = 0
            unused_capacity_reason: str | None = None
            steps: list[dict[str, object]] = []
            ok = True

            processed, queue_error = process_vm_queue()
            write_heartbeat(
                status="running",
                phase="cycle_start",
                cycle=cycle,
                started_at=cycle_started_at,
                current_command=None,
                heartbeat_interval_seconds=heartbeat_interval,
                vm_command_bus_last_processed=processed,
                vm_command_bus_error=queue_error,
                **capacity_snapshot(
                    cycle_started_monotonic=cycle_started_monotonic,
                    cycle_budget_seconds=cycle_budget_seconds,
                    active_work_seconds=active_work_seconds,
                    actions_completed_in_cycle=actions_completed_in_cycle,
                ),
            )

            while actions_completed_in_cycle < max_actions_per_cycle:
                elapsed = time.monotonic() - cycle_started_monotonic
                remaining = cycle_budget_seconds - elapsed
                action_budget = remaining - sync_reserve_seconds
                if action_budget < min_action_window_seconds:
                    unused_capacity_reason = "cycle_budget_reserve_boundary"
                    break

                processed, queue_error = process_vm_queue()
                write_heartbeat(
                    status="running",
                    phase="autonomous_action_start",
                    cycle=cycle,
                    started_at=cycle_started_at,
                    current_command=" ".join(AUTONOMY_COMMAND),
                    heartbeat_interval_seconds=heartbeat_interval,
                    vm_command_bus_last_processed=processed,
                    vm_command_bus_error=queue_error,
                    **capacity_snapshot(
                        cycle_started_monotonic=cycle_started_monotonic,
                        cycle_budget_seconds=cycle_budget_seconds,
                        active_work_seconds=active_work_seconds,
                        actions_completed_in_cycle=actions_completed_in_cycle,
                    ),
                )
                result = run_command(
                    AUTONOMY_COMMAND,
                    cycle=cycle,
                    heartbeat_interval=heartbeat_interval,
                    steps_completed=len(steps),
                    cycle_started_monotonic=cycle_started_monotonic,
                    cycle_budget_seconds=cycle_budget_seconds,
                    active_work_seconds_before=active_work_seconds,
                    actions_completed_in_cycle=actions_completed_in_cycle,
                    hard_timeout_seconds=action_budget,
                )
                steps.append(result)
                active_work_seconds += float(result["duration_s"])
                actions_completed_in_cycle += 1

                if bool(result.get("timed_out")):
                    ok = False
                    unused_capacity_reason = "autonomous_action_hit_cycle_time_limit"
                    break
                if int(result.get("returncode") or 0) != 0:
                    consecutive_failures += 1
                    ok = False
                    if consecutive_failures >= 2:
                        unused_capacity_reason = "bounded_backoff_after_consecutive_failures"
                        break
                else:
                    consecutive_failures = 0

                if once:
                    unused_capacity_reason = "run_once_test_mode"
                    break

            if actions_completed_in_cycle >= max_actions_per_cycle and unused_capacity_reason is None:
                unused_capacity_reason = "batch_limit_rollover_without_idle"

            remaining = max(0.0, cycle_budget_seconds - (time.monotonic() - cycle_started_monotonic))
            if (ROOT / SYNC_COMMAND[1]).exists() and remaining > 1.0:
                sync_result = run_command(
                    SYNC_COMMAND,
                    cycle=cycle,
                    heartbeat_interval=heartbeat_interval,
                    steps_completed=len(steps),
                    cycle_started_monotonic=cycle_started_monotonic,
                    cycle_budget_seconds=cycle_budget_seconds,
                    active_work_seconds_before=active_work_seconds,
                    actions_completed_in_cycle=actions_completed_in_cycle,
                    hard_timeout_seconds=remaining,
                )
                sync_result["role"] = "state_sync_overhead"
                steps.append(sync_result)
                overhead_seconds += float(sync_result["duration_s"])
                if int(sync_result.get("returncode") or 0) != 0:
                    ok = False

            processed, queue_error = process_vm_queue()
            final_capacity = capacity_snapshot(
                cycle_started_monotonic=cycle_started_monotonic,
                cycle_budget_seconds=cycle_budget_seconds,
                active_work_seconds=active_work_seconds,
                actions_completed_in_cycle=actions_completed_in_cycle,
                unused_capacity_reason=unused_capacity_reason,
            )
            write_heartbeat(
                status="healthy" if ok else "degraded",
                phase="cycle_complete",
                cycle=cycle,
                started_at=cycle_started_at,
                finished_at=now_iso(),
                heartbeat_interval_seconds=heartbeat_interval,
                current_command=None,
                steps=steps,
                overhead_seconds=round(overhead_seconds, 2),
                work_conserving_scheduler=True,
                vm_command_bus_last_processed=processed,
                vm_command_bus_error=queue_error,
                **final_capacity,
            )

            if once:
                return 0 if ok else 1
            if unused_capacity_reason == "bounded_backoff_after_consecutive_failures":
                time.sleep(failure_backoff_seconds)
            # No normal full-cycle sleep: successful workers immediately roll into
            # the next time budget and keep selecting safe useful work.
    finally:
        try:
            os.close(lock_fd)
        finally:
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
