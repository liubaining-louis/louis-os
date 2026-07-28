from __future__ import annotations

import unittest

from atlas.automation_compatibility import policy_rejection_reason, reject_incompatible_delivery_methods


class AutomationCompatibilityPolicyTests(unittest.TestCase):
    def test_rejects_exact_bulk_lyrics_production_false_positive(self) -> None:
        opportunity = {
            "title": "Bulk Lyrics Copy & Clean",
            "description": (
                "Copy every lyric for 500 songs from Genius, AZLyrics or MetroLyrics, "
                "clean section headers and deliver one text file per song."
            ),
            "payment_evidence": ["$4 - $8 / hr"],
            "decision": {"status": "capability_build", "blockers": [], "missing_capabilities": ["structured_document_delivery"]},
            "metadata": {"submission_dossier_prepared": False},
        }
        self.assertEqual(policy_rejection_reason(opportunity), "copyright_reproduction_risk")
        rows, rejected = reject_incompatible_delivery_methods([opportunity])
        self.assertEqual(rejected, 1)
        self.assertEqual(rows[0]["decision"]["status"], "rejected")
        self.assertFalse(rows[0]["metadata"]["capability_gap_allowed"])

    def test_rejects_hourly_rate_below_cash_first_floor(self) -> None:
        opportunity = {
            "title": "Simple structured data cleanup",
            "description": "Normalize a supplied CSV with clear fields.",
            "payment_evidence": ["$6 - $9 per hour"],
        }
        self.assertEqual(policy_rejection_reason(opportunity), "hourly_rate_below_cash_first_floor")

    def test_accepts_rights_cleared_and_viable_hourly_work(self) -> None:
        opportunity = {
            "title": "Clean client-owned product catalogue",
            "description": "Normalize a client-owned CSV and return a validated output file.",
            "payment_evidence": ["$20 - $30 / hr"],
        }
        self.assertIsNone(policy_rejection_reason(opportunity))


if __name__ == "__main__":
    unittest.main()
