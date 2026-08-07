#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HEARTBEAT = RESULTS / "vm_worker_heartbeat.json"
LOCK = ROOT / ".vm_monetization_worker.lock"

DEFAULT_COMMANDS = [
    [sys.executable, "scripts/universal_market_cycle.py"],
    [sys.executable, "scripts/cash_first_recovery_cycle.py"],
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_heartbeat(**extra: object) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "worker": "gcp_vm_monetization_worker",
        "updated_at": now_iso(),
        "pid": os.getpid(),
        **extra,
    }
    HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: list[str]) -> dict[str, object]:
    started = time.monotonic()
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": proc.returncode,
        "duration_s": round(time.monotonic() - started, 2),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def acquire_lock() -> int:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError:
        raise SystemExit("another VM monetization worker is already running")


def main() -> int:
    interval = max(60, int(os.getenv("LOUIS_VM_INTERVAL_SECONDS", "300")))
    once = os.getenv("LOUIS_VM_RUN_ONCE", "0") == "1"
    lock_fd = acquire_lock()
    cycle = 0
    try:
        while True:
            cycle += 1
            started_at = now_iso()
            write_heartbeat(status="running", cycle=cycle, started_at=started_at)
            steps = []
            ok = True
            for command in DEFAULT_COMMANDS:
                if not (ROOT / command[1]).exists():
                    steps.append({"command": command, "skipped": True, "reason": "script_missing"})
                    continue
                result = run_command(command)
                steps.append(result)
                if result["returncode"] != 0:
                    ok = False
                    break
            write_heartbeat(
                status="healthy" if ok else "degraded",
                cycle=cycle,
                started_at=started_at,
                finished_at=now_iso(),
                interval_seconds=interval,
                steps=steps,
            )
            if once:
                return 0 if ok else 1
            time.sleep(interval)
    finally:
        try:
            os.close(lock_fd)
        finally:
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
