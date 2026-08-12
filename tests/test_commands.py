from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from atlas.commands import create_command, get_command, list_commands


class CommandTests(unittest.TestCase):
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

    def test_low_risk_command_executes(self) -> None:
        mission = SimpleNamespace(mission_id="m-1", result="done")
        with patch("atlas.commands.run_mission", return_value=mission):
            command = create_command(
                order="Compare three supplier offers",
                context={"domain": "business"},
                idempotency_key="cmd-1",
            )
        self.assertEqual(command["status"], "completed")
        self.assertEqual(command["mission_id"], "m-1")
        self.assertEqual(get_command(command["command_id"])["result"], "done")

    def test_high_risk_command_requires_approval(self) -> None:
        with patch("atlas.commands.run_mission") as run_mission:
            command = create_command(
                order="Send an email to the supplier",
                idempotency_key="cmd-2",
            )
        self.assertEqual(command["status"], "approval_required")
        run_mission.assert_not_called()

    def test_authorized_5_50_usdc_discovery_uses_deterministic_route(self) -> None:
        outcome = {
            "status": "completed",
            "evidence": ["results/universal_internet_market.json"],
            "reason": "bounded discovery refresh completed",
        }
        order = (
            "Authorized deterministic 5–50 USDC discovery refresh. "
            "Execute cash-first micro-mission market refresh now, search all configured sources, "
            "and return agent-executable candidates."
        )
        with patch("atlas.commands.run_cash_first_usdc_cycle", return_value=outcome) as cycle:
            command = create_command(order=order, idempotency_key="cmd-usdc")
        self.assertEqual(command["status"], "completed")
        self.assertEqual(command["execution_mode"], "deterministic_cash_first_usdc_discovery_executor")
        self.assertEqual(command["evidence"], ["results/universal_internet_market.json"])
        cycle.assert_called_once_with(self.root)

    def test_runtime_deliverable_is_embedded_in_deterministic_result(self) -> None:
        workspace = self.root / "results" / "monetization_workspaces" / "candidate-1"
        workspace.mkdir(parents=True)
        artifact = workspace / "deliverable.md"
        artifact.write_text("# Deliverable\n\nReadable runtime content.\n", encoding="utf-8")
        outcome = {
            "status": "completed",
            "evidence": ["results/monetization_workspaces/candidate-1/deliverable.md"],
            "receipt": {
                "artifact_path": str(artifact),
                "artifact_sha256": "abc123",
            },
        }
        order = (
            "Authorized deterministic 5–50 USDC discovery refresh. "
            "Execute cash-first micro-mission market refresh now, search all configured sources, "
            "and return agent-executable candidates."
        )
        with patch("atlas.commands.run_cash_first_usdc_cycle", return_value=outcome):
            command = create_command(order=order, idempotency_key="cmd-deliverable")
        result = json.loads(command["result"])
        self.assertEqual(result["deliverable"]["content"], "# Deliverable\n\nReadable runtime content.\n")
        self.assertEqual(result["deliverable"]["sha256"], "abc123")
        self.assertFalse(result["deliverable"]["truncated"])

    def test_runtime_deliverable_refuses_paths_outside_workspace_root(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("must not leak", encoding="utf-8")
        outcome = {
            "status": "completed",
            "evidence": ["results/safe.json"],
            "receipt": {"artifact_path": str(outside)},
        }
        order = (
            "Authorized deterministic 5–50 USDC discovery refresh. "
            "Execute cash-first micro-mission market refresh now, search all configured sources, "
            "and return agent-executable candidates."
        )
        with patch("atlas.commands.run_cash_first_usdc_cycle", return_value=outcome):
            command = create_command(order=order, idempotency_key="cmd-no-leak")
        result = json.loads(command["result"])
        self.assertNotIn("deliverable", result)

    def test_generic_external_action_is_not_unlocked_by_usdc_word_alone(self) -> None:
        with patch("atlas.commands.run_mission") as run_mission:
            command = create_command(
                order="Send an email asking for 25 USDC payment",
                idempotency_key="cmd-usdc-email",
            )
        self.assertEqual(command["status"], "approval_required")
        run_mission.assert_not_called()

    def test_idempotency_prevents_duplicate_execution(self) -> None:
        mission = SimpleNamespace(mission_id="m-2", result="done")
        with patch("atlas.commands.run_mission", return_value=mission) as run_mission:
            first = create_command("Analyse the market", idempotency_key="same")
            second = create_command("Analyse the market", idempotency_key="same")
        self.assertEqual(first["command_id"], second["command_id"])
        self.assertEqual(run_mission.call_count, 1)
        self.assertEqual(len(list_commands()), 1)

    def test_empty_order_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_command("   ")


if __name__ == "__main__":
    unittest.main()
