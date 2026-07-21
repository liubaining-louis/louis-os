import unittest

from atlas.cash_first import CashFirstController, RevenueAction, north_star


class CashFirstControllerTests(unittest.TestCase):
    def test_empty_pipeline_requires_paid_offer(self):
        result = CashFirstController().evaluate("service-a", [])
        self.assertFalse(result.first_payment_received)
        self.assertIn("paid offer", result.next_best_action)

    def test_qualified_interest_requires_follow_up(self):
        actions = [
            RevenueAction("a1", "service-a", "outreach", "2026-07-21T08:00:00Z", qualified_response=True),
            RevenueAction("a2", "service-a", "follow_up", "2026-07-22T08:00:00Z"),
        ]
        result = CashFirstController(minimum_follow_ups=3).evaluate("service-a", actions)
        self.assertEqual(result.decision, "continue")
        self.assertIn("follow-up", result.primary_blocker)

    def test_no_signal_after_bounded_test_pivots(self):
        actions = [
            RevenueAction(f"a{i}", "service-a", "outreach", f"2026-07-{i + 1:02d}T08:00:00Z")
            for i in range(8)
        ]
        result = CashFirstController(minimum_actions_before_pivot=8).evaluate("service-a", actions)
        self.assertEqual(result.decision, "pivot")
        self.assertIn("no qualified market signal", result.primary_blocker)

    def test_profitable_payment_accelerates(self):
        actions = [
            RevenueAction("a1", "service-a", "outreach", "2026-07-21T08:00:00Z", cost=5),
            RevenueAction("a2", "service-a", "payment", "2026-07-23T08:00:00Z", gross_revenue=100),
        ]
        result = CashFirstController().evaluate("service-a", actions)
        self.assertEqual(result.decision, "accelerate")
        self.assertTrue(result.first_payment_received)
        self.assertEqual(result.net_revenue, 95)
        self.assertEqual(result.days_to_first_payment, 2)

    def test_north_star_is_cash_not_activity(self):
        policy = north_star()
        self.assertIn("verified net cash", policy["priority_rule"])
        self.assertIn("first_payment_received", policy["required_kpis"])


if __name__ == "__main__":
    unittest.main()
