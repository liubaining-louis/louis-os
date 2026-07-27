from __future__ import annotations

import unittest

from scripts.sync_cash_first_ledger import synchronize


class CashFirstLedgerSyncTests(unittest.TestCase):
    def test_syncs_pipeline_without_inventing_submission_or_revenue(self) -> None:
        ledger = {
            "external_actions_submitted": 0,
            "internet_actions_submitted": 0,
            "conversions": 0,
            "revenue_confirmed_eur": 0.0,
            "revenue_received": 0.0,
        }
        portfolio = {
            "generated_at": "2026-07-27T08:00:00+00:00",
            "counts": {"cash_first": 3, "strategic": 10, "human_action_ready": 1},
            "top_cash_first": {"opportunity_id": "market-one", "reward_amount": 40.0, "currency": "USD"},
        }
        human = {"new_count": 1, "notification_required": True}
        cycle = {
            "generated_at": "2026-07-27T08:01:00+00:00",
            "simple_mission_sources_refreshed": ["freelancer_public_simple_jobs"],
            "simple_mission_opportunities_observed": 5,
            "simple_mission_dossiers_prepared": 1,
            "next_action": "notify_owner_and_complete_exact_human_gate",
        }
        result = synchronize(ledger, portfolio, human, cycle)
        self.assertEqual(result["cash_first_candidates"], 3)
        self.assertEqual(result["human_action_ready"], 1)
        self.assertEqual(result["simple_mission_dossiers_prepared"], 1)
        self.assertEqual(result["external_actions_submitted"], 0)
        self.assertEqual(result["internet_actions_submitted"], 0)
        self.assertEqual(result["conversions"], 0)
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)

    def test_preserves_existing_receipt_backed_totals(self) -> None:
        ledger = {
            "external_actions_submitted": 2,
            "internet_actions_submitted": 2,
            "conversions": 1,
            "revenue_confirmed_eur": 12.5,
            "revenue_received": 12.5,
        }
        result = synchronize(ledger, {"counts": {}}, {}, {})
        self.assertEqual(result["external_actions_submitted"], 2)
        self.assertEqual(result["conversions"], 1)
        self.assertEqual(result["revenue_confirmed_eur"], 12.5)


if __name__ == "__main__":
    unittest.main()
