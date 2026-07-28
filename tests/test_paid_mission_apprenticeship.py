import unittest

from atlas.paid_mission_apprenticeship import coach, determine_stage


class PaidMissionApprenticeshipTests(unittest.TestCase):
    def test_prepared_is_not_submitted(self):
        record = {"proposal_ready": True}
        self.assertEqual(determine_stage(record), "proposal_ready")
        self.assertIn("submission_receipt", coach(record).missing_evidence)

    def test_accepted_is_not_paid(self):
        record = {"acceptance_receipt": "client-approved"}
        self.assertEqual(determine_stage(record), "accepted")
        self.assertIn("payment_request_receipt", coach(record).missing_evidence)

    def test_payment_request_is_not_payment(self):
        record = {"payment_request_receipt": "invoice-001"}
        self.assertEqual(determine_stage(record), "payment_requested")
        self.assertIn("payment_receipt", coach(record).missing_evidence)

    def test_paid_requires_payment_receipt(self):
        record = {"payment_receipt": "bank-or-platform-receipt"}
        self.assertEqual(determine_stage(record), "paid")
        self.assertEqual(coach(record).missing_evidence, [])

    def test_scope_agreement_precedes_material_work(self):
        decision = coach({"client_response_receipt": "reply"})
        self.assertEqual(decision.stage, "response_received")
        self.assertIn("do not start material work", decision.stop_condition)


if __name__ == "__main__":
    unittest.main()
