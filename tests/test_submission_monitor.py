import unittest

from scripts.autonomous_submission_monitor import derive_action


class SubmissionMonitorTests(unittest.TestCase):
    def test_merged_pr_moves_to_reward_verification(self):
        status, action = derive_action({"merged_at": "2026-07-26T00:00:00Z", "state": "closed"}, [], [])
        self.assertEqual(status, "merged")
        self.assertEqual(action, "verify_reward_and_payout_status")

    def test_requested_changes_take_priority(self):
        status, action = derive_action(
            {"merged_at": None, "state": "open"},
            [{"state": "CHANGES_REQUESTED"}],
            [{"status": "completed", "conclusion": "success"}],
        )
        self.assertEqual(status, "changes_requested")
        self.assertEqual(action, "translate_maintainer_feedback_into_patch_revision")

    def test_failed_ci_triggers_repair_loop(self):
        status, action = derive_action(
            {"merged_at": None, "state": "open"},
            [],
            [{"status": "completed", "conclusion": "failure"}],
        )
        self.assertEqual(status, "ci_failed")
        self.assertEqual(action, "fetch_logs_reproduce_fix_test_and_update_same_pull_request")

    def test_open_successful_pr_waits_without_spam(self):
        status, action = derive_action(
            {"merged_at": None, "state": "open"},
            [],
            [{"status": "completed", "conclusion": "success"}],
        )
        self.assertEqual(status, "awaiting_maintainer")
        self.assertIn("without_spam", action)


if __name__ == "__main__":
    unittest.main()
