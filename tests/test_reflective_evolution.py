from __future__ import annotations

import unittest

from atlas.reflective_evolution import diagnose, review_previous


class ReflectiveEvolutionTests(unittest.TestCase):
    def test_detects_preparation_without_action(self) -> None:
        result = diagnose({
            "opportunities_observed": 20,
            "opportunities_eligible": 12,
            "dossiers_prepared": 10,
            "external_submissions_verified": 0,
            "sources_total": 5,
        })
        self.assertEqual(result.weakness_id, "preparation-without-action")
        self.assertIn("submission", result.corrective_action.lower())

    def test_detects_market_message_mismatch(self) -> None:
        result = diagnose({
            "opportunities_observed": 20,
            "opportunities_eligible": 10,
            "dossiers_prepared": 7,
            "external_submissions_verified": 5,
            "replies_verified": 0,
            "sources_total": 5,
        })
        self.assertEqual(result.weakness_id, "market-message-mismatch")
        self.assertIn("controlled", result.corrective_action.lower())

    def test_balances_source_expansion(self) -> None:
        result = diagnose({"sources_total": 1})
        self.assertEqual(result.weakness_id, "source-concentration")
        self.assertIn("noise", result.balancing_counter_risk.lower())

    def test_previous_action_review_is_evidence_based(self) -> None:
        review = review_previous(
            {"weakness_id": "preparation-without-action", "success_metric": "one submission"},
            {"external_submissions_verified": 1},
        )
        self.assertTrue(review["improved"])

    def test_does_not_claim_sentience(self) -> None:
        result = diagnose({})
        self.assertNotIn("conscious", result.principal_weakness.lower())


if __name__ == "__main__":
    unittest.main()
