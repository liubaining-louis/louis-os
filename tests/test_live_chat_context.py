from __future__ import annotations

import unittest
from unittest.mock import patch

from atlas.server import build_live_prompt


class LiveChatContextTests(unittest.TestCase):
    def test_build_live_prompt_injects_canonical_live_state_and_question(self) -> None:
        with (
            patch("atlas.server.prompt_context", return_value='{"autonomous_worker":{"status":"running"}}'),
            patch("atlas.server.live_prompt_context", return_value='{"worker":"gcp_vm_monetization_worker","phase":"command_start"}'),
        ):
            prompt = build_live_prompt("Quel est ton statut maintenant ?")
        self.assertIn('"status":"running"', prompt)
        self.assertIn('"worker":"gcp_vm_monetization_worker"', prompt)
        self.assertIn("Quel est ton statut maintenant ?", prompt)
        self.assertIn("CANONICAL OPERATIONAL STATE", prompt)
        self.assertIn("LIVE VM HEARTBEAT", prompt)
        self.assertIn("Do not claim fresher data than these snapshots", prompt)


if __name__ == "__main__":
    unittest.main()
