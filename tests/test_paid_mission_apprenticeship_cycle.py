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

    def test_prepare_then_gate_is_qualified(self) -> None:
        market = {
            "cash_first_top_opportunity": {
                "opportunity_id": "market-1",
                "title": "API fix",
                "decision_status": "prepare_then_gate",
                "prepared_artifacts": ["results/x/proposal.md"],
                "human_gate_required": True,
            }
        }
        with patch("scripts.paid_mission_apprenticeship_cycle.proposal_is_ready", return_value=True):
            record = build_record(market)
        self.assertTrue(record["qualified"])
        self.assertTrue(record["proposal_ready"])
        self.assertTrue(record["human_gate_required"])
        self.assertFalse(record["external_submission_verified"])

    def test_artifacts_must_exist(self) -> None:
        self.assertFalse(proposal_is_ready({"prepared_artifacts": ["does/not/exist.md"]}))


if __name__ == "__main__":
    unittest.main()
