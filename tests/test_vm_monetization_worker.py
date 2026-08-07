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
        self.assertIn(payload["status"], {"healthy", "degraded"})
        self.assertGreaterEqual(payload["cycle"], 1)
        self.assertIn("steps", payload)

    def test_systemd_service_restarts(self) -> None:
        service = (ROOT / "deploy" / "louis-os-monetization.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", service)
        self.assertIn("vm_monetization_worker.py", service)


if __name__ == "__main__":
    unittest.main()
