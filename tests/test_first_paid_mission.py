import unittest

from atlas.first_paid_mission import evaluate


class FirstPaidMissionTests(unittest.TestCase):
    def test_rejects_language_identity_mismatch(self):
        decision = evaluate({
            "title": "Native Thai voice recording",
            "fresh_open_verified": True,
            "payment_path": "platform escrow",
            "acceptance_criteria": "accepted audio",
            "effort_hours": 2,
            "capability_fit": 0.9,
            "personal_eligibility_required": True,
            "legal_policy_pass": True,
        })
        self.assertFalse(decision.eligible)
        self.assertIn("personal_eligibility_required", decision.reasons)

    def test_accepts_narrow_csv_job(self):
        decision = evaluate({
            "title": "Deduplicate and normalize CSV export",
            "fresh_open_verified": True,
            "payment_path": "fixed price escrow",
            "acceptance_criteria": "no duplicate IDs and schema validation passes",
            "effort_hours": 3,
            "capability_fit": 0.95,
            "legal_policy_pass": True,
            "human_actions_required": 1,
            "reward_eur": 90,
            "payment_confidence": 0.9,
            "competition_risk": 0.2,
        })
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.recommended_offer, "csv_rescue")
        self.assertGreater(decision.score, 0)

    def test_rejects_claimed_bounty(self):
        decision = evaluate({
            "title": "API integration bounty",
            "fresh_open_verified": True,
            "payment_path": "merge reward",
            "acceptance_criteria": "tests pass and PR merged",
            "effort_hours": 6,
            "capability_fit": 0.9,
            "active_competing_claim": True,
            "legal_policy_pass": True,
        })
        self.assertFalse(decision.eligible)
        self.assertIn("active_competing_claim", decision.reasons)


if __name__ == "__main__":
    unittest.main()
