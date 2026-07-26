from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "command-bridge.yml"
).read_text(encoding="utf-8")


class CommandBridgeEvidenceContractTests(unittest.TestCase):
    def test_completed_status_requires_non_empty_evidence(self) -> None:
        self.assertIn('STATUS" == "completed" && "$EVIDENCE_COUNT" == "0"', WORKFLOW)
        self.assertIn("evidence_contract_violation", WORKFLOW)

    def test_issue_report_surfaces_execution_mode_evidence_and_diagnosis(self) -> None:
        self.assertIn("Execution mode", WORKFLOW)
        self.assertIn("Evidence count", WORKFLOW)
        self.assertIn("**Diagnosis**", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
