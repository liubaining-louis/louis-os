from __future__ import annotations

import json
import unittest

from atlas.github_reward_issue_source import GitHubRewardIssueSource


class GitHubRewardIssueSourceTests(unittest.TestCase):
    def _issue(self) -> dict:
        return {
            "state": "open",
            "html_url": "https://github.com/acme/project/issues/42",
            "url": "https://api.github.com/repos/acme/project/issues/42",
            "comments_url": "https://api.github.com/repos/acme/project/issues/42/comments",
            "title": "Fix README typo",
            "body": "Correct one deterministic typo and add a regression assertion.",
            "assignees": [],
        }

    def test_accepts_open_issue_with_trusted_platform_reward_comment(self) -> None:
        def fetcher(url: str) -> bytes:
            if "/search/issues" in url:
                return json.dumps({"items": [self._issue()]}).encode()
            if url.endswith("/comments?per_page=100"):
                return json.dumps([
                    {
                        "user": {"login": "algora-pbc[bot]"},
                        "body": "A $75 reward is available at https://algora.io/acme/bounties/reward-42",
                        "html_url": "https://github.com/acme/project/issues/42#issuecomment-1",
                    }
                ]).encode()
            raise AssertionError(url)

        rows, state = GitHubRewardIssueSource(
            queries=("is:issue is:open label:bounty",),
            fetcher=fetcher,
        ).collect()

        self.assertEqual(state.status, "ok")
        self.assertEqual(len(rows), 1)
        opportunity = rows[0]
        self.assertEqual(opportunity.reward_amount, 75.0)
        self.assertTrue(opportunity.reward_verified)
        self.assertEqual(opportunity.required_capabilities, ("deterministic_text_replacement",))
        self.assertEqual(opportunity.metadata["platform"], "Algora")
        self.assertTrue(opportunity.metadata["status_verified_open"])

    def test_rejects_untrusted_issue_title_amount(self) -> None:
        issue = self._issue()
        issue["title"] = "$500 bounty for README typo"

        def fetcher(url: str) -> bytes:
            if "/search/issues" in url:
                return json.dumps({"items": [issue]}).encode()
            if url.endswith("/comments?per_page=100"):
                return json.dumps([
                    {
                        "user": {"login": "random-user"},
                        "body": "$500 bounty available",
                        "html_url": "https://github.com/acme/project/issues/42#issuecomment-2",
                    }
                ]).encode()
            raise AssertionError(url)

        rows, state = GitHubRewardIssueSource(
            queries=("is:issue is:open label:bounty",),
            fetcher=fetcher,
        ).collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "empty")

    def test_rejects_crowded_or_already_solved_issue(self) -> None:
        def fetcher(url: str) -> bytes:
            if "/search/issues" in url:
                return json.dumps({"items": [self._issue()]}).encode()
            if url.endswith("/comments?per_page=100"):
                return json.dumps([
                    {
                        "user": {"login": "opire[bot]"},
                        "body": "$100 USD reward: https://app.opire.dev/issues/42",
                        "html_url": "https://github.com/acme/project/issues/42#issuecomment-3",
                    },
                    {"user": {"login": "solver-a"}, "body": "/attempt", "html_url": "x"},
                    {"user": {"login": "solver-b"}, "body": "/try", "html_url": "y"},
                ]).encode()
            raise AssertionError(url)

        rows, state = GitHubRewardIssueSource(
            queries=("is:issue is:open label:bounty",),
            maximum_attempts=1,
            fetcher=fetcher,
        ).collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "empty")


if __name__ == "__main__":
    unittest.main()
