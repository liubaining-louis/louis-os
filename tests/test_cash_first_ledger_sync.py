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
            "simple_mission_sources_refreshed": ["freelancer_public_simple_jobs", "freelancer_public_software_jobs"],
            "simple_mission_opportunities_observed": 5,
            "simple_mission_dossiers_prepared": 1,
            "software_micro_mission_engine": "active",
            "software_micro_mission_capability_count": 5,
            "software_micro_mission_validated_demo_count": 3,
            "software_micro_missions_matched": 4,
            "software_micro_missions_accepted": 2,
            "software_micro_missions_rejected": 2,
            "software_micro_mission_dossiers_prepared": 1,
            "next_action": "notify_owner_and_complete_exact_human_gate",
        }
        result = synchronize(ledger, portfolio, human, cycle)
        self.assertEqual(result["cash_first_candidates"], 3)
        self.assertEqual(result["human_action_ready"], 1)
        self.assertEqual(result["simple_mission_dossiers_prepared"], 1)
        self.assertEqual(result["software_micro_mission_engine"], "active")
        self.assertEqual(result["software_micro_mission_capability_count"], 5)
        self.assertEqual(result["software_micro_mission_validated_demo_count"], 3)
        self.assertEqual(result["software_micro_missions_accepted"], 2)
        self.assertEqual(result["software_micro_mission_dossiers_prepared"], 1)
        self.assertEqual(result["external_actions_submitted"], 0)
        self.assertEqual(result["internet_actions_submitted"], 0)
        self.assertEqual(result["conversions"], 0)
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)
        self.assertIsNone(result["net_profit_eur"])
        self.assertEqual(result["cost_basis_status"], "incomplete_cost_basis")
        self.assertIn("gcp_compute", result["unknown_cost_components"])

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
        self.assertIsNone(result["net_profit_eur"])

    def test_computes_net_profit_only_with_complete_cost_basis(self) -> None:
        ledger = {"revenue_confirmed_eur": 12.5, "revenue_received": 12.5}
        costs = {
            "components": {
                "gcp_compute": {"known": True, "eur": 1.0},
                "model_api": {"known": True, "eur": 0.5},
                "github_actions": {"known": True, "eur": 0.0},
                "transaction_fees": {"known": True, "eur": 0.25},
            }
        }
        result = synchronize(ledger, {"counts": {}}, {}, {}, costs)
        self.assertEqual(result["cost_basis_status"], "complete")
        self.assertEqual(result["known_operating_cost_eur"], 1.75)
        self.assertEqual(result["net_profit_eur"], 10.75)
        self.assertEqual(result["unknown_cost_components"], [])


if __name__ == "__main__":
    unittest.main()
