from __future__ import annotations

import unittest

from scripts.apply_github_admin_hardening import GITHUB_ACTIONS_APP_ID, REQUIRED_CHECKS, desired_ruleset


class GitHubAdminHardeningTests(unittest.TestCase):
    def test_ruleset_targets_default_branch_and_is_active(self) -> None:
        payload = desired_ruleset()
        self.assertEqual(payload["target"], "branch")
        self.assertEqual(payload["enforcement"], "active")
        self.assertEqual(payload["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])

    def test_github_actions_is_explicit_bypass_actor(self) -> None:
        payload = desired_ruleset()
        self.assertEqual(
            payload["bypass_actors"],
            [{"actor_id": GITHUB_ACTIONS_APP_ID, "actor_type": "Integration", "bypass_mode": "always"}],
        )

    def test_ruleset_blocks_deletion_and_force_push(self) -> None:
        types = {rule["type"] for rule in desired_ruleset()["rules"]}
        self.assertIn("deletion", types)
        self.assertIn("non_fast_forward", types)

    def test_ruleset_requires_pull_request_and_both_ci_checks(self) -> None:
        rules = {rule["type"]: rule for rule in desired_ruleset()["rules"]}
        pr = rules["pull_request"]["parameters"]
        self.assertEqual(pr["required_approving_review_count"], 0)
        self.assertTrue(pr["required_review_thread_resolution"])
        checks = rules["required_status_checks"]["parameters"]
        self.assertTrue(checks["strict_required_status_checks_policy"])
        self.assertEqual(
            [row["context"] for row in checks["required_status_checks"]],
            REQUIRED_CHECKS,
        )
        self.assertTrue(all(row["integration_id"] == GITHUB_ACTIONS_APP_ID for row in checks["required_status_checks"]))


if __name__ == "__main__":
    unittest.main()
