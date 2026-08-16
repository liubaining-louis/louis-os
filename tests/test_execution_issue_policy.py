from __future__ import annotations

import unittest

from scripts.enforce_execution_issue_policy import candidate_marker, plan_issue_actions, ticket_candidate, violation_reason


POLICY = {
    "external_actions_enabled": True,
    "kill_switch": False,
    "max_autonomous_effort_hours": 3.0,
    "max_reward_usd_equivalent": 500.0,
    "require_verified_payment_path": True,
    "allowed_families": ["light_technical"],
    "blocked_terms": ["hackathon", "protocol engineering", "security exploit", "security assessment", "wallet integration"],
}


def internal_issue(reward: float, title: str = "[ATLAS execution] Small fix", *, number: int = 1, marker: str = "abc"):
    return {
        "number": number,
        "title": title,
        "body": f"<!-- atlas-candidate:{marker} -->\n- Reward hint: {reward} USD\n",
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

    def test_high_risk_wallet_integration_is_rejected(self) -> None:
        issue = internal_issue(150, "[ATLAS execution] Add wallet integration support")
        self.assertEqual(violation_reason(issue, POLICY), "blocked_term:wallet integration")

    def test_external_contributor_issue_is_ignored(self) -> None:
        issue = internal_issue(2000)
        issue["user"] = {"login": "external-contributor"}
        self.assertIsNone(ticket_candidate(issue))
        self.assertIsNone(violation_reason(issue, POLICY))

    def test_unmarked_issue_is_ignored(self) -> None:
        issue = internal_issue(2000)
        issue["body"] = "ordinary repository issue"
        self.assertIsNone(violation_reason(issue, POLICY))

    def test_candidate_marker_is_deterministic(self) -> None:
        self.assertEqual(candidate_marker(internal_issue(10, marker="same-candidate")), "same-candidate")

    def test_duplicate_candidate_tickets_keep_only_newest_policy_compliant_ticket(self) -> None:
        issues = [
            internal_issue(10, number=10, marker="dup"),
            internal_issue(10, number=20, marker="dup"),
            internal_issue(10, number=15, marker="other"),
        ]
        actions = plan_issue_actions(issues, POLICY)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["issue_number"], 10)
        self.assertEqual(actions[0]["reason"], "duplicate_internal_candidate_ticket")

    def test_policy_violation_closes_all_duplicates(self) -> None:
        issues = [
            internal_issue(2000, number=10, marker="bad"),
            internal_issue(2000, number=20, marker="bad"),
        ]
        actions = plan_issue_actions(issues, POLICY)
        self.assertEqual({row["issue_number"] for row in actions}, {10, 20})
        self.assertTrue(all(row["reason"] == "reward_exceeds_quick_win_strategy_cap" for row in actions))

    def test_external_pr_is_not_touched(self) -> None:
        issue = internal_issue(2000, number=50)
        issue["pull_request"] = {"url": "https://api.github.com/pulls/50"}
        self.assertEqual(plan_issue_actions([issue], POLICY), [])


if __name__ == "__main__":
    unittest.main()
