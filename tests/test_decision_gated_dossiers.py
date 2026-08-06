from __future__ import annotations

import unittest

from atlas.decision_gated_dossiers import build_pipeline


class DecisionGatedDossierTests(unittest.TestCase):
    def valid(self, **overrides):
        item = {
            "opportunity_id": "job-1",
            "title": "Small CSV cleanup",
            "canonical_url": "https://example.test/jobs/1",
            "listing_open": True,
            "buyer_seeking_worker": True,
            "reward_verified": True,
            "acceptance_criteria": ["clean CSV", "validation note"],
            "remote_eligible": True,
            "platform_compliant": True,
            "estimated_hours": 2,
            "reward_amount": 40,
            "currency": "EUR",
            "evidence": ["https://example.test/jobs/1"],
        }
        item.update(overrides)
        return item

    def test_verified_case_produces_prepare_then_gate_dossier(self):
        result = build_pipeline([self.valid()])
        self.assertEqual(result["prepare_then_gate"], 1)
        self.assertEqual(result["execute_now"], 0)
        self.assertFalse(result["dossiers"][0]["external_submission_verified"])
        self.assertTrue(result["dossiers"][0]["receipt_required"])

    def test_missing_evidence_does_not_produce_dossier(self):
        result = build_pipeline([self.valid(listing_open=None)])
        self.assertEqual(result["prepare_then_gate"], 0)
        self.assertEqual(result["decisions"][0]["decision"], "verify_then_reconsider")

    def test_policy_blocked_opportunity_is_rejected(self):
        result = build_pipeline([self.valid(platform_compliant=False, title="Proxy anti-bot bypass")])
        self.assertEqual(result["prepare_then_gate"], 0)
        self.assertEqual(result["decisions"][0]["decision"], "reject")

    def test_low_hourly_value_is_rejected(self):
        result = build_pipeline([self.valid(estimated_hours=10, reward_amount=20)])
        self.assertEqual(result["prepare_then_gate"], 0)
        self.assertIn("economically_unviable", result["decisions"][0]["blockers"])

    def test_pipeline_never_invents_submission_or_revenue(self):
        result = build_pipeline([self.valid()])
        self.assertEqual(result["external_submissions_verified"], 0)
        self.assertEqual(result["revenue_verified_eur"], 0)
        self.assertTrue(result["submission_contract"]["success_without_receipt_forbidden"])


if __name__ == "__main__":
    unittest.main()
