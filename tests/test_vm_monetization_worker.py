from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VmMonetizationWorkerTests(unittest.TestCase):
    def test_worker_run_once_writes_heartbeat(self) -> None:
        heartbeat = ROOT / "results" / "vm_worker_heartbeat.json"
        heartbeat.unlink(missing_ok=True)
        env = os.environ.copy()
        env["LOUIS_VM_RUN_ONCE"] = "1"
        env["LOUIS_VM_INTERVAL_SECONDS"] = "60"
        env["LOUIS_VM_HEARTBEAT_SECONDS"] = "5"
        # Unit test must not depend on ADC/network access.
        env["LOUIS_LIVE_STATE_FIRESTORE"] = "0"
        proc = subprocess.run(
            [sys.executable, "scripts/vm_monetization_worker.py"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertIn(proc.returncode, (0, 1))
        self.assertTrue(heartbeat.exists())
        payload = json.loads(heartbeat.read_text(encoding="utf-8"))
        self.assertEqual(payload["worker"], "gcp_vm_monetization_worker")
        self.assertEqual(payload["schema_version"], "2.0")
        self.assertIn(payload["status"], {"healthy", "degraded"})
        self.assertEqual(payload["phase"], "cycle_complete")
        self.assertGreaterEqual(payload["cycle"], 1)
        self.assertEqual(payload["heartbeat_interval_seconds"], 5)
        self.assertIn("execute_now", payload)
        self.assertIn("prepare_then_gate", payload)
        self.assertIn("external_submissions_verified", payload)
        self.assertIn("revenue_verified_eur", payload)
        self.assertIn("steps", payload)
        commands = [step.get("command") for step in payload["steps"] if isinstance(step, dict)]
        self.assertTrue(any(command and "sync_operational_state_to_firestore.py" in command for command in commands))

    def test_systemd_service_restarts_and_publishes_live_state(self) -> None:
        service = (ROOT / "deploy" / "louis-os-monetization.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", service)
        self.assertIn("vm_monetization_worker.py", service)
        self.assertIn("LOUIS_VM_HEARTBEAT_SECONDS=10", service)
        self.assertIn("LOUIS_LIVE_STATE_FIRESTORE=1", service)


if __name__ == "__main__":
    unittest.main()
