#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
STATUS_PATH = RESULTS / "gcp_self_bootstrap.json"
METADATA_BASE = "http://metadata.google.internal/computeMetadata/v1"
METADATA_HEADERS = {"Metadata-Flavor": "Google"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def metadata(path: str, timeout: float = 0.8) -> str | None:
    req = urllib.request.Request(f"{METADATA_BASE}/{path.lstrip('/')}" , headers=METADATA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8").strip() or None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def run(command: list[str], *, timeout: int = 30) -> dict[str, object]:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def detect_environment() -> dict[str, object]:
    zone_full = metadata("instance/zone")
    instance_name = metadata("instance/name")
    project_id = metadata("project/project-id")
    internal_ip = metadata("instance/network-interfaces/0/ip")
    external_ip = metadata("instance/network-interfaces/0/access-configs/0/external-ip")
    instance_id = metadata("instance/id")
    is_gce = bool(instance_name and project_id and zone_full)
    return {
        "is_gce": is_gce,
        "project_id": project_id,
        "instance_name": instance_name,
        "instance_id": instance_id,
        "zone": zone_full.rsplit("/", 1)[-1] if zone_full else None,
        "internal_ip": internal_ip,
        "external_ip": external_ip,
        "linux_user": getpass.getuser(),
        "hostname": socket.gethostname(),
        "repo_root": str(ROOT),
        "python": sys.executable,
    }


def sudo_noninteractive_available() -> bool:
    if os.geteuid() == 0:
        return True
    if not shutil.which("sudo"):
        return False
    proc = subprocess.run(["sudo", "-n", "true"], text=True, capture_output=True)
    return proc.returncode == 0


def repo_state() -> dict[str, object]:
    if not (ROOT / ".git").exists():
        return {"git_checkout": False}
    status = run(["git", "status", "--porcelain"], timeout=10)
    branch = run(["git", "branch", "--show-current"], timeout=10)
    return {
        "git_checkout": True,
        "branch": str(branch.get("stdout_tail") or "").strip(),
        "tracked_worktree_dirty": bool(str(status.get("stdout_tail") or "").strip()),
    }


def write_status(payload: dict[str, object]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def install_service(environment: dict[str, object]) -> dict[str, object]:
    if not environment.get("is_gce"):
        return {"attempted": False, "installed": False, "blocker": "not_running_on_gce"}
    if not (ROOT / "scripts" / "install_vm_monetization_worker.sh").exists():
        return {"attempted": False, "installed": False, "blocker": "installer_missing"}
    state = repo_state()
    if state.get("tracked_worktree_dirty"):
        return {"attempted": False, "installed": False, "blocker": "git_worktree_dirty", "repo_state": state}
    if not sudo_noninteractive_available():
        return {
            "attempted": False,
            "installed": False,
            "blocker": "sudo_noninteractive_unavailable",
            "required_human_action": "grant this VM user passwordless permission for systemctl/copy or run installer once interactively",
        }

    env = os.environ.copy()
    env["LOUIS_REPO_DIR"] = str(ROOT)
    proc = subprocess.run(
        ["bash", "scripts/install_vm_monetization_worker.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    result: dict[str, object] = {
        "attempted": True,
        "installed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    if proc.returncode == 0:
        active = subprocess.run(
            ["systemctl", "is-active", "louis-os-monetization.service"],
            text=True,
            capture_output=True,
        )
        result["service_active"] = active.returncode == 0 and active.stdout.strip() == "active"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-detect and bootstrap Louis OS on a Google Compute Engine VM.")
    parser.add_argument("--install", action="store_true", help="attempt service installation using the current VM identity")
    args = parser.parse_args()

    environment = detect_environment()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "updated_at": now_iso(),
        "environment": environment,
        "repo_state": repo_state(),
        "security": {
            "private_keys_collected": False,
            "access_tokens_collected": False,
            "metadata_identity_only": True,
        },
    }
    if args.install:
        payload["installation"] = install_service(environment)
    else:
        payload["installation"] = {
            "attempted": False,
            "installed": False,
            "next_action": "run with --install on the VM when autonomous installation is authorized",
        }
    write_status(payload)
    print(json.dumps(payload, ensure_ascii=False))
    installation = payload.get("installation") if isinstance(payload.get("installation"), dict) else {}
    if args.install and installation.get("attempted") and not installation.get("installed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
