from __future__ import annotations

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
