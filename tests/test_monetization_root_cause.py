import unittest

from atlas.monetization_root_cause import analyze_monetization


class MonetizationRootCauseTests(unittest.TestCase):
    def test_no_candidates_is_the_primary_root_cause(self):
        result = analyze_monetization(ledger={}, candidates=[])
        self.assertEqual(result.primary_cause.code, "no_qualified_opportunity")
        self.assertIn("3 qualified opportunities", result.primary_cause.success_metric)
        self.assertEqual(result.time_to_first_euro_band, "first euro not currently reachable")

    def test_all_gated_candidates_trigger_source_pivot(self):
        candidates = [
            {
                "readiness_status": "gated_external_prerequisite",
                "external_prerequisites_cleared": False,
            }
            for _ in range(4)
        ]
        result = analyze_monetization(ledger={}, candidates=candidates)
        self.assertEqual(result.primary_cause.code, "all_opportunities_gated")
        self.assertEqual(result.primary_cause.confidence, 0.99)
        self.assertIn("executable_candidate_rate", result.primary_cause.success_metric)

    def test_executable_candidate_without_submission_is_detected(self):
        candidates = [
            {
                "readiness_status": "executable_now",
                "external_prerequisites_cleared": True,
            }
        ]
        result = analyze_monetization(
            ledger={"external_actions_submitted": 0},
            candidates=candidates,
            external_actions=[{"tested_deliverable": True, "status": "ready"}],
        )
        self.assertEqual(result.primary_cause.code, "executable_work_not_submitted")
        self.assertIn("verified external submission", result.primary_cause.success_metric)

    def test_submitted_action_without_response_requires_bounded_follow_up(self):
        candidates = [
            {
                "readiness_status": "executable_now",
                "external_prerequisites_cleared": True,
            }
        ]
        result = analyze_monetization(
            ledger={"external_actions_submitted": 1, "qualified_replies": 0},
            candidates=candidates,
            external_receipts=[{"verified": True}],
        )
        self.assertEqual(result.primary_cause.code, "submitted_without_market_response")
        self.assertIn("follow-up", result.primary_cause.corrective_action)

    def test_qualified_interest_without_conversion_is_detected(self):
        candidates = [
            {
                "readiness_status": "executable_now",
                "external_prerequisites_cleared": True,
            }
        ]
        result = analyze_monetization(
            ledger={"external_actions_submitted": 1, "qualified_replies": 2, "conversions": 0},
            candidates=candidates,
        )
        self.assertEqual(result.primary_cause.code, "interest_not_converted_to_payment_path")
        self.assertIn("priced offer", result.primary_cause.corrective_action)

    def test_verified_revenue_disables_zero_revenue_diagnosis(self):
        result = analyze_monetization(
            ledger={"revenue_confirmed_eur": 25},
            candidates=[],
        )
        self.assertEqual(result.primary_cause.code, "no_active_zero_revenue_cause")
        self.assertEqual(result.time_to_first_euro_band, "already achieved")

    def test_verified_conversion_outranks_an_empty_current_candidate_pool(self):
        result = analyze_monetization(
            ledger={
                "external_actions_submitted": 8,
                "qualified_replies": 3,
                "conversions": 3,
                "revenue_confirmed_eur": 0,
            },
            candidates=[],
            external_receipts=[{"verified": True}] * 8,
        )
        self.assertEqual(result.primary_cause.code, "conversion_without_verified_payment")
        self.assertEqual(result.time_to_first_euro_band, "possible within 1-7 days if the payment path is completed")

    def test_authoritative_queue_becomes_the_specific_primary_cause(self):
        result = analyze_monetization(
            ledger={
                "external_actions_submitted": 8,
                "qualified_replies": 3,
                "conversions": 3,
                "payouts_queued": 3,
                "payout_queued_rtc": 11,
                "revenue_confirmed_eur": 0,
            },
            candidates=[],
        )
        self.assertEqual(result.primary_cause.code, "accepted_payout_waiting_settlement")
        self.assertIn("wallet balance increase", result.primary_cause.success_metric)

    def test_received_crypto_is_not_misreported_as_eur(self):
        result = analyze_monetization(
            ledger={
                "conversions": 3,
                "revenue_received_rtc": 11,
                "revenue_confirmed_eur": 0,
            },
            candidates=[],
        )
        self.assertEqual(result.primary_cause.code, "crypto_received_without_verified_eur_liquidity")
        self.assertIn("first EUR remains unverified", result.time_to_first_euro_band)


if __name__ == "__main__":
    unittest.main()
