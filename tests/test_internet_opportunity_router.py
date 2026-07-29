from __future__ import annotations

import unittest

from atlas.internet_opportunity_router import next_pivot, route


class InternetOpportunityRouterTests(unittest.TestCase):
    def test_execute_now_for_verified_csv_mission(self) -> None:
        result = route({
            "title": "Urgent CSV cleanup and deduplication",
            "description": "Normalize columns and deliver a cleaned CSV",
            "capability_fit": 0.95,
            "effort_hours": 3,
            "fresh_open_verified": True,
            "payment_path": "fixed-price milestone",
            "acceptance_criteria": ["clean file", "duplicate report"],
            "legal_policy_pass": True,
            "human_actions_required": 0,
            "reward_eur": 90,
            "payment_confidence": 0.9,
            "competition_risk": 0.2,
        })
        self.assertEqual(result.domain, "data_csv")
        self.assertEqual(result.lane, "exploit")
        self.assertEqual(result.decision, "execute_now")
        self.assertGreater(result.score, 0)

    def test_prepare_then_gate_for_one_account_action(self) -> None:
        result = route({
            "title": "Fix one API webhook",
            "description": "Reproduce, patch and test an API integration",
            "capability_fit": 0.90,
            "effort_hours": 5,
            "fresh_open_verified": True,
            "payment_path": "platform milestone",
            "acceptance_criteria": ["test passes"],
            "legal_policy_pass": True,
            "human_actions_required": 1,
            "reward_eur": 150,
            "payment_confidence": 0.8,
        })
        self.assertEqual(result.decision, "prepare_then_gate")

    def test_rejects_personal_language_eligibility(self) -> None:
        result = route({
            "title": "Native interpreter needed",
            "description": "Live legal interpretation",
            "fresh_open_verified": True,
            "payment_path": "milestone",
            "acceptance_criteria": ["live attendance"],
            "legal_policy_pass": True,
            "personal_eligibility_required": True,
            "effort_hours": 4,
        })
        self.assertEqual(result.decision, "reject")
        self.assertIn("personal_eligibility_required", result.reasons)

    def test_capability_build_requires_verified_market_signal(self) -> None:
        result = route({
            "title": "Create a small digital template",
            "description": "Reusable Notion template",
            "capability_fit": 0.5,
            "effort_hours": 6,
            "fresh_open_verified": True,
            "payment_path": "marketplace payout",
            "acceptance_criteria": ["template delivered"],
            "legal_policy_pass": True,
            "market_signal_verified": True,
        })
        self.assertEqual(result.decision, "capability_build")

    def test_pivot_rules(self) -> None:
        self.assertEqual(next_pivot({"rejected_without_candidate": 30}), "regenerate_queries_and_shift_domain")
        self.assertEqual(next_pivot({"source_results_without_eligible": 50}), "pause_source_and_replace")
        self.assertEqual(next_pivot({"proposals_without_reply": 5}), "change_offer_or_message")
        self.assertEqual(next_pivot({"verified_payments": 1}), "expand_similar_searches")


if __name__ == "__main__":
    unittest.main()
