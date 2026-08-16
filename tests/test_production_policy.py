from __future__ import annotations

import unittest

from atlas.production_policy import evaluate_candidate, preflight


POLICY = {
    "external_actions_enabled": True,
    "kill_switch": False,
    "max_autonomous_effort_hours": 3.0,
    "max_reward_usd_equivalent": 500.0,
    "require_verified_payment_path": True,
    "allowed_families": ["research", "python_automation", "light_technical"],
    "blocked_terms": ["full stack", "security exploit", "protocol engineering"],
}


class ProductionPolicyTests(unittest.TestCase):
    def test_kill_switch_fails_closed(self) -> None:
        policy = dict(POLICY, kill_switch=True)
        decision = preflight(policy)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "global_kill_switch_active")

    def test_external_actions_can_be_disabled(self) -> None:
        policy = dict(POLICY, external_actions_enabled=False)
        decision = preflight(policy)
        self.assertFalse(decision.allowed)

    def test_rejects_large_reward_in_quick_win_mode(self) -> None:
        decision = evaluate_candidate(
            {
                "title": "Large technical bounty",
                "reward_amount": 2000,
                "effort_hours": 2,
                "family": "light_technical",
                "payment_path": "escrow",
            },
            POLICY,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "reward_exceeds_quick_win_strategy_cap")

    def test_rejects_long_effort(self) -> None:
        decision = evaluate_candidate(
            {
                "title": "API automation",
                "reward_amount": 100,
                "effort_hours": 8,
                "family": "python_automation",
                "payment_path": "escrow",
            },
            POLICY,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "effort_exceeds_quick_win_limit")

    def test_rejects_blocked_technical_project(self) -> None:
        decision = evaluate_candidate(
            {
                "title": "Full stack protocol engineering project",
                "reward_amount": 100,
                "effort_hours": 2,
                "family": "light_technical",
                "payment_path": "escrow",
            },
            POLICY,
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.reason.startswith("blocked_term:"))

    def test_rejects_unknown_payment_path(self) -> None:
        decision = evaluate_candidate(
            {
                "title": "Research task",
                "reward_amount": 25,
                "effort_hours": 2,
                "family": "research",
            },
            POLICY,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "payment_path_unknown")

    def test_accepts_bounded_verified_quick_win(self) -> None:
        decision = evaluate_candidate(
            {
                "title": "Research and summarize API docs",
                "reward_amount": 25,
                "effort_hours": 2,
                "family": "research",
                "payment_path": "escrowed USDC",
            },
            POLICY,
        )
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
