from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.commands import create_command
from atlas.evidence_grounding import evidence_gate_error, normalize_evidence, requires_external_evidence


class EvidenceGroundingTests(unittest.TestCase):
    def test_detects_connected_data_mission(self) -> None:
        self.assertTrue(requires_external_evidence("Analyse tous les e-mails Gmail sur le charbon"))
        self.assertFalse(requires_external_evidence("Rédige une présentation générale du charbon"))

    def test_rejects_missing_evidence(self) -> None:
        error = evidence_gate_error("Analyse mes e-mails Gmail", {})
        self.assertIsNotNone(error)
        self.assertIn("Refusing to fabricate", error or "")

    def test_accepts_structured_evidence(self) -> None:
        context = {
            "evidence": [{
                "source": "gmail",
                "reference": "thread-123",
                "content": "Subject: Ogatan quotation\nFrom: buyer@example.com\nBody: Please quote one container.",
            }]
        }
        self.assertIsNone(evidence_gate_error("Analyse mes e-mails Gmail", context))
        self.assertEqual(len(normalize_evidence(context)), 1)

    def test_command_stops_before_llm_when_evidence_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"COMMAND_STORE": "local"}, clear=False), \
                 patch("atlas.commands._local_dir", return_value=Path(tmp)), \
                 patch("atlas.commands.run_mission") as run_mission:
                command = create_command(
                    "Analyse tous les e-mails Gmail concernant le charbon",
                    context={},
                    idempotency_key="evidence-test",
                )
        self.assertEqual(command["status"], "blocked")
        self.assertIn("external_evidence_required", command["error"])
        run_mission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
