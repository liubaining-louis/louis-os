from __future__ import annotations

import unittest

from atlas.production_policy import evaluate_candidate
from scripts.autonomous_opportunity_executor import marker_in_issues, policy_candidate


POLICY = {
    "external_actions_enabled": True,
    "kill_switch": False,
    "max_autonomous_effort_hours": 3.0,
    "max_reward_usd_equivalent": 500.0,
    "require_verified_payment_path": True,
    "allowed_families": ["light_technical"],
    "blocked_terms": ["hackathon", "wallet integration", "security assessment"],
}


class AutonomousOpportunityExecutorPolicyTests(unittest.TestCase):
    def test_reward_hint_flows_into_global_policy(self) -> None:
        candidate = {
            "title": "Large bounty",
            "reward_hint": 2000,
            "payment_evidence": ["authoritative receipt"],
        }
        decision = evaluate_candidate(policy_candidate(candidate), POLICY)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "reward_exceeds_quick_win_strategy_cap")

    def test_payment_evidence_maps_to_verified_payment_path(self) -> None:
        candidate = {
            "title": "Small fix",
            "reward_hint": 10,
            "payment_evidence": ["escrow evidence"],
        }
        mapped = policy_candidate(candidate)
        self.assertTrue(mapped["reward_verified"])
        self.assertEqual(mapped["payment_path"], "authoritative_payment_evidence")
        self.assertTrue(evaluate_candidate(mapped, POLICY).allowed)

    def test_github_marker_idempotency_finds_closed_or_open_issue(self) -> None:
        issues = [
            {
                "number": 10,
                "body": "<!-- atlas-candidate:abc -->",
                "html_url": "https://github.com/example/repo/issues/10",
                "state": "closed",
            },
            {
                "number": 15,
                "body": "<!-- atlas-candidate:abc -->",
                "html_url": "https://github.com/example/repo/issues/15",
                "state": "open",
            },
        ]
        found = marker_in_issues(issues, "abc")
        self.assertIsNotNone(found)
        self.assertEqual(found["number"], 15)

    def test_github_marker_ignores_pull_requests(self) -> None:
        issues = [
            {
                "number": 20,
                "body": "<!-- atlas-candidate:abc -->",
                "pull_request": {"url": "https://api.github.com/pulls/20"},
            }
        ]
        self.assertIsNone(marker_in_issues(issues, "abc"))


if __name__ == "__main__":
    unittest.main()
