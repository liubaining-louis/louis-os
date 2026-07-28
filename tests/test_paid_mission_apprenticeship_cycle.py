from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.paid_mission_apprenticeship_cycle import build_record, proposal_is_ready


class PaidMissionApprenticeshipCycleTests(unittest.TestCase):
    def test_empty_market_keeps_zero_state(self) -> None:
        record = build_record({})
        self.assertIsNone(record["opportunity_id"])
        self.assertFalse(record["qualified"])
        self.assertFalse(record["proposal_ready"])
        self.assertEqual(record["revenue_verified_eur"], 0.0)

    def test_ineligible_low_value_candidate_is_rejected(self) -> None:
        market = {
            "cash_first_top_opportunity": {
                "opportunity_id": "market-1",
                "title": "Payment Gateway Fix",
                "decision_status": "prepare_then_gate",
                "estimated_effort_hours": 12,
                "estimated_hourly_value": 1.08,
                "prepared_artifacts": ["results/x/proposal.md"],
                "payment_methods": ["platform milestone"],
                "human_actions": ["authorize account"],
            }
        }
        with patch("scripts.paid_mission_apprenticeship_cycle.proposal_is_ready", return_value=True):
            record = build_record(market)
        self.assertFalse(record["qualified"])
        self.assertFalse(record["proposal_ready"])
        self.assertIn("effort_above_first_mission_limit", record["accelerator_gate"]["reasons"])
        self.assertIn("status_not_freshly_verified_open", record["accelerator_gate"]["reasons"])

    def test_strictly_eligible_candidate_can_be_selected(self) -> None:
        market = {
            "cash_first_top_opportunity": {
                "opportunity_id": "market-2",
                "title": "CSV data cleaning and deduplication",
                "lane": "cash_first",
                "fresh_open_verified": True,
                "acceptance_criteria": ["clean CSV", "duplicate report"],
                "estimated_effort_hours": 4,
                "capability_fit": 0.9,
                "legal_policy_pass": True,
                "payment_methods": ["platform milestone"],
                "payment_confidence": 0.9,
                "competition_risk": 0.2,
                "currency": "EUR",
                "reward_amount": 100,
                "prepared_artifacts": ["results/x/proposal.md"],
                "human_actions": ["authorize account"],
            }
        }
        with patch("scripts.paid_mission_apprenticeship_cycle.proposal_is_ready", return_value=True):
            record = build_record(market)
        self.assertTrue(record["qualified"])
        self.assertTrue(record["proposal_ready"])
        self.assertTrue(record["accelerator_gate"]["eligible"])

    def test_artifacts_must_exist(self) -> None:
        self.assertFalse(proposal_is_ready({"prepared_artifacts": ["does/not/exist.md"]}))


if __name__ == "__main__":
    unittest.main()
