from __future__ import annotations

import unittest

from scripts.enforce_execution_issue_policy import ticket_candidate, violation_reason


POLICY = {
    "external_actions_enabled": True,
    "kill_switch": False,
    "max_autonomous_effort_hours": 3.0,
    "max_reward_usd_equivalent": 500.0,
    "require_verified_payment_path": True,
    "allowed_families": ["light_technical"],
    "blocked_terms": ["hackathon", "protocol engineering", "security exploit"],
}


def internal_issue(reward: float, title: str = "[ATLAS execution] Small fix"):
    return {
        "title": title,
        "body": f"<!-- atlas-candidate:abc -->\n- Reward hint: {reward} USD\n",
        "user": {"login": "github-actions[bot]"},
    }


class ExecutionIssuePolicyTests(unittest.TestCase):
    def test_large_internal_ticket_is_rejected(self) -> None:
        self.assertEqual(
            violation_reason(internal_issue(2000), POLICY),
            "reward_exceeds_quick_win_strategy_cap",
        )

    def test_small_internal_ticket_survives_reward_gate(self) -> None:
        self.assertIsNone(violation_reason(internal_issue(10), POLICY))

    def test_blocked_family_word_is_rejected(self) -> None:
        issue = internal_issue(100, "[ATLAS execution] Hackathon protocol engineering")
        self.assertTrue((violation_reason(issue, POLICY) or "").startswith("blocked_term:"))

    def test_external_contributor_issue_is_ignored(self) -> None:
        issue = internal_issue(2000)
        issue["user"] = {"login": "external-contributor"}
        self.assertIsNone(ticket_candidate(issue))
        self.assertIsNone(violation_reason(issue, POLICY))

    def test_unmarked_issue_is_ignored(self) -> None:
        issue = internal_issue(2000)
        issue["body"] = "ordinary repository issue"
        self.assertIsNone(violation_reason(issue, POLICY))


if __name__ == "__main__":
    unittest.main()
