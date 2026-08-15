#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "louis_mission_bridge.py"


def call(args: list[str], env: dict[str, str]) -> dict:
    cp = subprocess.run(["python3", str(SCRIPT), *args], env=env, text=True, capture_output=True)
    if cp.returncode != 0:
        raise AssertionError(f"command failed: {args}\nstdout={cp.stdout}\nstderr={cp.stderr}")
    return json.loads(cp.stdout)


def b64(value: object) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env["LOUIS_MISSION_BRIDGE_DIR"] = td
        context = {
            "public": "safe task context",
            "api_key": "sk-proj-FAKEFAKEFAKEFAKE123456",
            "nested": {"authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
            "log": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\nnormal line",
        }
        out = call([
            "request", "--request-id", "mbr_test_1", "--mission-id", "job-1",
            "--source", "test", "--objective", "solve public task", "--blocker", "test blocker",
            "--requested-output", "return a patch", "--context-b64", b64(context), "--risk", "low",
        ], env)
        assert out == {"status": "queued", "request_id": "mbr_test_1"}

        pending = call(["pending"], env)
        raw = json.dumps(pending)
        assert pending["status"] == "pending"
        assert pending["request"]["context"]["public"] == "safe task context"
        assert "FAKEFAKE" not in raw
        assert "abcdefghijklmnopqrstuvwxyz123456" not in raw
        assert "[REDACTED_SENSITIVE_FIELD]" in raw

        published = call(["mark-published", "--request-id", "mbr_test_1", "--comment-id", "123"], env)
        assert published["status"] == "published"
        assert call(["pending"], env)["status"] == "empty"

        response = {"next_step": "run tests", "patch": "safe example"}
        answered = call(["answer", "--request-id", "mbr_test_1", "--response-b64", b64(response)], env)
        assert answered["status"] == "answered"
        assert call(["status", "--request-id", "mbr_test_1"], env)["has_response"] is True

        first = call(["consume", "--request-id", "mbr_test_1"], env)
        second = call(["consume", "--request-id", "mbr_test_1"], env)
        assert first["status"] == "consumed" and first["response"] == response
        assert second["status"] == "consumed" and second["response"] == response

        # Duplicate request ids are idempotent and cannot overwrite an existing mission.
        dup = call([
            "request", "--request-id", "mbr_test_1", "--mission-id", "different",
            "--source", "test", "--objective", "overwrite", "--blocker", "overwrite",
        ], env)
        assert dup["status"] == "exists"

    print("MISSION_BRIDGE_TESTS=PASS")


if __name__ == "__main__":
    main()
