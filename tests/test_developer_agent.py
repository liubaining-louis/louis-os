from __future__ import annotations

import unittest

from atlas.developer_agent import build_dossier, dossier_markdown, validate_proposal


class DeveloperAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal = {
            "proposal_id": "abc1234567890def",
            "capability": "autonomous_execution",
            "title": "Complete one approved external action end-to-end",
            "rationale": "Current score 3/10. No completed action.",
            "acceptance_criteria": [
                "An approved action transitions to completed or blocked",
                "Every side effect has evidence",
            ],
        }

    def test_build_dossier_is_guarded_and_actionable(self) -> None:
        dossier = build_dossier(self.proposal)
        self.assertEqual(dossier["proposal_id"], self.proposal["proposal_id"])
        self.assertEqual(dossier["status"], "ready_for_implementation")
        self.assertTrue(dossier["branch"].startswith("atlas/improve-autonomous-execution-"))
        self.assertTrue(dossier["promotion_gate"]["tests_pass"])
        self.assertTrue(dossier["promotion_gate"]["direct_main_push_forbidden"])
        self.assertFalse(dossier["promotion_gate"]["automatic_merge"])

    def test_markdown_contains_idempotency_marker(self) -> None:
        body = dossier_markdown(build_dossier(self.proposal))
        self.assertIn("louis-proposal-id:abc1234567890def", body)
        self.assertIn("Acceptance criteria", body)
        self.assertIn("No direct mutation", body)

    def test_invalid_proposal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_proposal({"proposal_id": "x"})


if __name__ == "__main__":
    unittest.main()
