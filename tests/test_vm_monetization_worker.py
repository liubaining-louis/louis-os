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
        env["LOUIS_VM_CYCLE_BUDGET_SECONDS"] = "60"
        env["LOUIS_VM_SYNC_RESERVE_SECONDS"] = "10"
        env["LOUIS_VM_MIN_ACTION_WINDOW_SECONDS"] = "5"
        env["LOUIS_VM_MAX_ACTIONS_PER_CYCLE"] = "2"
        env["LOUIS_VM_HEARTBEAT_SECONDS"] = "5"
        env["LOUIS_LIVE_STATE_FIRESTORE"] = "0"
        env["LOUIS_VM_COMMAND_BUS"] = "0"
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
        self.assertEqual(payload["schema_version"], "3.1")
        self.assertIn(payload["status"], {"healthy", "degraded"})
        self.assertEqual(payload["phase"], "cycle_complete")
        self.assertGreaterEqual(payload["cycle"], 1)
        self.assertEqual(payload["heartbeat_interval_seconds"], 5)
        self.assertIn("execute_now", payload)
        self.assertIn("external_submissions_verified", payload)
        self.assertIn("revenue_verified_eur", payload)
        self.assertIn("autonomy_action", payload)
        self.assertIn("autonomy_status", payload)
        self.assertIn("vm_command_bus_last_processed", payload)
        self.assertIn("steps", payload)
        self.assertTrue(payload["work_conserving_scheduler"])
        self.assertEqual(payload["cycle_budget_seconds"], 60)
        self.assertGreaterEqual(payload["actions_completed_in_cycle"], 1)
        self.assertGreaterEqual(payload["active_work_seconds"], 0)
        self.assertGreaterEqual(payload["productive_utilization_pct"], 0)
        self.assertLessEqual(payload["productive_utilization_pct"], 100)
        self.assertIn("unused_capacity_reason", payload)

    def test_worker_contract_is_time_aware_and_work_conserving(self) -> None:
        source = (ROOT / "scripts" / "vm_monetization_worker.py").read_text(encoding="utf-8")
        self.assertIn("process_pending_vm_commands", source)
        self.assertIn("scripts/autonomy_cycle.py", source)
        self.assertIn("scripts/sync_operational_state_to_firestore.py", source)
        self.assertNotIn('[sys.executable, "scripts/universal_market_cycle.py"]', source)
        self.assertNotIn('[sys.executable, "scripts/cash_first_recovery_cycle.py"]', source)
        self.assertIn("LOUIS_VM_CYCLE_BUDGET_SECONDS", source)
        self.assertIn("LOUIS_VM_SYNC_RESERVE_SECONDS", source)
        self.assertIn("LOUIS_VM_MAX_ACTIONS_PER_CYCLE", source)
        self.assertIn("while actions_completed_in_cycle < max_actions_per_cycle", source)
        self.assertIn("cycle_budget_reserve_boundary", source)
        self.assertIn("batch_limit_rollover_without_idle", source)
        self.assertNotIn("idle_with_heartbeat", source)
        self.assertIn('db.collection(LIVE_COLLECTION).document(LIVE_DOCUMENT).set(payload)', source)
        self.assertIn('db.collection("louis_runtime").document("current").set(', source)
        self.assertIn('"productive_utilization_pct": payload.get("productive_utilization_pct")', source)

    def test_multi_model_review_is_advisory_not_submission_gate(self) -> None:
        source = (ROOT / "scripts" / "multi_model_monetization_cycle.py").read_text(encoding="utf-8")
        self.assertIn('"multi_model_policy": "advisory_non_blocking"', source)
        self.assertIn('"submission_ai_gate": "advisory_only"', source)
        self.assertNotIn("blocked_pending_critic_pass", source)

    def test_systemd_service_restarts_and_publishes_live_state(self) -> None:
        service = (ROOT / "deploy" / "louis-os-monetization.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", service)
        self.assertIn("vm_monetization_worker.py", service)
        self.assertIn("LOUIS_VM_HEARTBEAT_SECONDS=10", service)
        self.assertIn("LOUIS_VM_CYCLE_BUDGET_SECONDS=300", service)
        self.assertIn("LOUIS_VM_SYNC_RESERVE_SECONDS=20", service)
        self.assertIn("LOUIS_VM_MAX_ACTIONS_PER_CYCLE=12", service)
        self.assertIn("LOUIS_LIVE_STATE_FIRESTORE=1", service)


if __name__ == "__main__":
    unittest.main()
