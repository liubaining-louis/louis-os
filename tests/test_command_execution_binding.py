from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.commands import create_command


class CommandExecutionBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"COMMAND_STORE": "local"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.root_patch = patch("atlas.commands.ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_allowlisted_cycle_uses_deterministic_executor_not_llm(self) -> None:
        outcome = {
            "status": "completed",
            "execution_mode": "deterministic_internal_executor",
            "result": "created",
            "evidence": ["results/workspace/SCOPE.md", "results/workspace/execution_receipt.json"],
            "diagnosis": {"root_cause": "generic route was not an executor"},
        }
        with (
            patch("atlas.commands.run_verified_deliverable_cycle", return_value=outcome) as execute,
            patch("atlas.commands.run_mission") as run_mission,
        ):
            command = create_command(
                "Execute verified monetization deliverable cycle",
                context={"domain": "non_charcoal_monetization"},
                idempotency_key="deterministic-1",
            )

        self.assertEqual(command["status"], "completed")
        self.assertEqual(command["execution_mode"], "deterministic_internal_executor")
        self.assertEqual(len(command["evidence"]), 2)
        self.assertEqual(command["diagnosis"]["root_cause"], "generic route was not an executor")
        execute.assert_called_once_with(self.root)
        run_mission.assert_not_called()

    def test_completed_without_evidence_is_failed(self) -> None:
        outcome = {
            "status": "completed",
            "execution_mode": "deterministic_internal_executor",
            "result": "prose only",
            "evidence": [],
        }
        with (
            patch("atlas.commands.run_verified_deliverable_cycle", return_value=outcome),
            patch("atlas.commands.run_mission") as run_mission,
        ):
            command = create_command(
                "Execute verified monetization deliverable cycle",
                idempotency_key="deterministic-2",
            )

        self.assertEqual(command["status"], "failed")
        self.assertIn("execution_completed_without_evidence", command["error"])
        self.assertEqual(command["diagnosis"]["resolution_class"], "AUTO_RESOLVABLE")
        run_mission.assert_not_called()

    def test_blocked_executor_preserves_causal_diagnosis(self) -> None:
        outcome = {
            "status": "blocked",
            "execution_mode": "deterministic_internal_executor",
            "reason": "no_authentic_executable_candidate",
            "evidence": ["results/monetization_execution_diagnosis.json"],
            "diagnosis": {
                "blocked_stage": "candidate_selection",
                "root_cause": "candidate data is stale",
                "resolution_class": "AUTO_RESOLVABLE",
                "next_action": "refresh_and_revalidate_candidates",
            },
        }
        with patch("atlas.commands.run_verified_deliverable_cycle", return_value=outcome):
            command = create_command(
                "Execute verified monetization deliverable cycle",
                idempotency_key="deterministic-3",
            )

        self.assertEqual(command["status"], "blocked")
        self.assertEqual(command["error"], "no_authentic_executable_candidate")
        self.assertEqual(command["diagnosis"]["next_action"], "refresh_and_revalidate_candidates")


if __name__ == "__main__":
    unittest.main()
