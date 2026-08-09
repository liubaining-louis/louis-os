from __future__ import annotations

import unittest

from atlas.mission_intelligence import (
    IntelligencePolicy,
    allocate_search,
    build_outcome_metrics,
    detect_stagnation,
    score_mission,
)


class MissionIntelligenceTests(unittest.TestCase):
    def test_unverified_advanced_stage_is_ignored(self) -> None:
        metrics = build_outcome_metrics([
            {"opportunity_id": "a", "stage": "submitted", "source_id": "x"},
            {"opportunity_id": "b", "stage": "paid", "source_id": "x", "verified_revenue_eur": 500},
        ])
        self.assertEqual(metrics["opportunities_with_latest_stage"], 0)
        self.assertEqual(metrics["verified_revenue_eur"], 0.0)

    def test_verified_payment_updates_metrics(self) -> None:
        metrics = build_outcome_metrics([
            {
                "opportunity_id": "a",
                "stage": "paid",
                "source_id": "market",
                "capability_id": "csv",
                "proposal_variant": "risk_reduction",
                "evidence": ["receipt-1"],
                "verified_revenue_eur": 120,
            }
        ])
        self.assertEqual(metrics["verified_revenue_eur"], 120.0)
        self.assertEqual(metrics["by_source"]["market"]["paid"], 1)

    def test_score_allows_long_work_by_default_but_keeps_operator_override(self) -> None:
        metrics = build_outcome_metrics([])
        twenty_hours = {
            "opportunity_id": "a",
            "reward_amount": 500,
            "metadata": {"estimated_effort_hours": 20, "time_to_cash_days": 10},
        }
        twelve_hours = {
            "opportunity_id": "b",
            "reward_amount": 500,
            "metadata": {"estimated_effort_hours": 12, "time_to_cash_days": 10},
        }
        slow = {
            "opportunity_id": "c",
            "reward_amount": 500,
            "metadata": {"estimated_effort_hours": 3, "time_to_cash_days": 60},
        }

        twenty_score = score_mission(twenty_hours, metrics)
        twelve_score = score_mission(twelve_hours, metrics)
        self.assertIsNotNone(twenty_score)
        self.assertIsNotNone(twelve_score)
        self.assertGreater(twelve_score.expected_value_per_hour_eur, twenty_score.expected_value_per_hour_eur)
        self.assertIsNone(score_mission(slow, metrics))

        strict = IntelligencePolicy(max_effort_hours=3)
        self.assertIsNone(score_mission(twelve_hours, metrics, strict))

    def test_validated_product_fit_improves_expected_value(self) -> None:
        metrics = build_outcome_metrics([])
        base = {
            "opportunity_id": "a",
            "source_id": "market",
            "reward_amount": 200,
            "required_capabilities": ["csv"],
            "metadata": {
                "estimated_effort_hours": 3,
                "time_to_cash_days": 14,
                "scope_clarity": 0.8,
                "client_quality": 0.8,
                "freshness_score": 0.9,
            },
        }
        low = score_mission(base, metrics)
        high_payload = {**base, "opportunity_id": "b", "metadata": {**base["metadata"], "validated_product_fit": 1.0}}
        high = score_mission(high_payload, metrics)
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertGreater(high.expected_value_eur, low.expected_value_eur)

    def test_search_allocation_keeps_exploration(self) -> None:
        metrics = {
            "by_source": {
                "proven": {"won": 1, "paid": 0, "prepared": 1},
                "adjacent": {"won": 0, "paid": 0, "prepared": 2},
            }
        }
        allocation = allocate_search(metrics)
        self.assertAlmostEqual(sum(allocation.values()), 1.0)
        self.assertGreaterEqual(allocation["experimental_sources"], 0.10)
        self.assertEqual(allocation["proven_sources"], 0.70)

    def test_stagnation_detects_activity_without_progress(self) -> None:
        events = [{"stage": "observed"} for _ in range(50)]
        actions = detect_stagnation(events, days_without_progress=14, policy=IntelligencePolicy())
        triggers = {item["trigger"] for item in actions}
        self.assertIn("discovery_without_preparation", triggers)
        self.assertIn("time_without_economic_progress", triggers)


if __name__ == "__main__":
    unittest.main()
