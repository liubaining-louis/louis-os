from __future__ import annotations

import unittest

from atlas.opportunity_truth_gate import verify_opportunity


class OpportunityTruthGateTests(unittest.TestCase):
    def opportunity(self, **overrides):
        values = {
            "source_url": "https://example.org/jobs/1",
            "title": "Merge Excel files",
            "description": "Merge one hundred spreadsheets into a clean workbook with normalized headers and a sortable final sheet.",
            "reward_amount": 80.0,
            "observed_at": "2026-08-05T10:00:00+00:00",
            "physical_presence_required": False,
            "metadata": {
                "days_left": 5,
                "estimated_effort_hours": 5,
                "reward_direction": "payer_to_worker",
                "buyer_seeking_worker": True,
            },
        }
        values.update(overrides)
        return values

    def test_verified_remote_payable_job_passes(self) -> None:
        result = verify_opportunity(self.opportunity())
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "verified_payable")
        self.assertEqual(result.blockers, ())

    def test_seller_offer_is_not_treated_as_job(self) -> None:
        result = verify_opportunity(
            self.opportunity(
                title="Rent AWS EC2 Servers at 50% Discount",
                description="We offer discount servers for sale. Buy now.",
            )
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "commercial_offer_not_job")

    def test_completed_payment_issue_is_rejected(self) -> None:
        result = verify_opportunity(
            self.opportunity(
                title="Payment for completed work",
                description="Pay contributor after work completed and already merged.",
            )
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "already_assigned")

    def test_in_person_work_is_geographically_ineligible(self) -> None:
        result = verify_opportunity(
            self.opportunity(
                title="Retail In-Person Sales Promoter Needed",
                description="Work in person as a store promoter for a local retail campaign.",
            )
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "geographically_ineligible")

    def test_anti_automation_bypass_is_policy_blocked(self) -> None:
        result = verify_opportunity(
            self.opportunity(
                title="Dynamic website extraction",
                description="Use a residential proxy to avoid detection and bypass CAPTCHA while extracting text.",
            )
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "platform_policy_blocked")

    def test_low_hourly_value_fails_closed(self) -> None:
        item = self.opportunity(reward_amount=10.0)
        item["metadata"] = {**item["metadata"], "estimated_effort_hours": 6}
        result = verify_opportunity(item)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "economically_unviable")

    def test_closed_listing_requires_revalidation(self) -> None:
        item = self.opportunity(observed_at="")
        item["metadata"] = {**item["metadata"], "days_left": 0}
        result = verify_opportunity(item)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "expired_or_closed")


if __name__ == "__main__":
    unittest.main()
