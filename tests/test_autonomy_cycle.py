from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import autonomy_cycle


class AutonomyCycleMarketPipelineTests(unittest.TestCase):
    def test_market_refresh_runs_complete_cash_first_pipeline(self) -> None:
        completed = {
            "status": "completed",
            "returncode": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }
        with patch.object(autonomy_cycle, "_run_script", return_value=completed) as run:
            outcome = autonomy_cycle.execute("market_refresh")

        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            list(autonomy_cycle.CASH_FIRST_MARKET_PIPELINE),
        )
        self.assertIn("scripts/refresh_simple_mission_sources.py", autonomy_cycle.CASH_FIRST_MARKET_PIPELINE)
        self.assertIn("scripts/prepare_simple_mission_dossiers.py", autonomy_cycle.CASH_FIRST_MARKET_PIPELINE)
        self.assertIn("scripts/sync_cash_first_ledger.py", autonomy_cycle.CASH_FIRST_MARKET_PIPELINE)
        self.assertNotIn("scripts/create_capability_gap_issues.py", autonomy_cycle.CASH_FIRST_MARKET_PIPELINE)

    def test_vm_rollout_watches_every_market_pipeline_script(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "provision-louis-os-vm.yml"
        ).read_text(encoding="utf-8")

        for relative in autonomy_cycle.CASH_FIRST_MARKET_PIPELINE:
            self.assertIn(f'- "{relative}"', workflow, relative)
        self.assertIn('- "atlas/*source*.py"', workflow)
        self.assertIn('- "atlas/universal_market.py"', workflow)
        self.assertIn('- "atlas/cash_first_market.py"', workflow)

    def test_market_refresh_fails_fast_with_causal_step(self) -> None:
        calls: list[str] = []

        def fake_run(relative: str, timeout: int = 240) -> dict[str, object]:
            calls.append(relative)
            if relative == "scripts/refresh_simple_mission_sources.py":
                return {
                    "status": "failed",
                    "returncode": 1,
                    "stdout_tail": "",
                    "stderr_tail": "source refresh failed",
                }
            return {
                "status": "completed",
                "returncode": 0,
                "stdout_tail": "",
                "stderr_tail": "",
            }

        with patch.object(autonomy_cycle, "_run_script", side_effect=fake_run):
            outcome = autonomy_cycle.execute("market_refresh")

        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["failed_step"], "scripts/refresh_simple_mission_sources.py")
        self.assertEqual(calls[-1], "scripts/refresh_simple_mission_sources.py")
        self.assertNotIn("scripts/prepare_simple_mission_dossiers.py", calls)


if __name__ == "__main__":
    unittest.main()
