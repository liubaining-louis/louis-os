from __future__ import annotations

import json
import unittest

from atlas.github_issue_verifier import verify_open_issue, verify_open_issues
from atlas.universal_market import InternetOpportunity


def opportunity(url: str = "https://github.com/old/repo/issues/7") -> InternetOpportunity:
    return InternetOpportunity(
        source_id="algora_public_bounties",
        source_category="code_bounty",
        source_url=url,
        title="stale title",
        description="board excerpt",
        reward_amount=50.0,
        currency="USD",
        reward_verified=True,
        payment_evidence=("https://algora.io/test/bounties?status=open",),
        required_capabilities=("technical_proposal",),
        observed_at="2026-07-26T00:00:00+00:00",
        account_required=True,
        terms_required=True,
        identity_or_kyc_required=True,
        evidence=(url,),
        metadata={"platform": "Algora"},
    )


class GitHubIssueVerifierTests(unittest.TestCase):
    def test_open_renamed_issue_becomes_canonical(self) -> None:
        payload = {
            "state": "open",
            "html_url": "https://github.com/new/repo/issues/7",
            "title": "Canonical title",
            "body": "Current scope",
            "updated_at": "2026-07-26T12:00:00Z",
        }
        result = verify_open_issue(opportunity(), fetcher=lambda _: json.dumps(payload).encode())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.source_url, payload["html_url"])
        self.assertEqual(result.title, payload["title"])
        self.assertTrue(result.metadata["github_state_verified"])
        self.assertIn("https://api.github.com/repos/old/repo/issues/7", result.payment_evidence)

    def test_closed_issue_is_rejected(self) -> None:
        payload = {"state": "closed", "html_url": "https://github.com/new/repo/issues/7", "title": "Done"}
        self.assertIsNone(verify_open_issue(opportunity(), fetcher=lambda _: json.dumps(payload).encode()))

    def test_pull_request_is_rejected(self) -> None:
        payload = {
            "state": "open",
            "html_url": "https://github.com/new/repo/pull/7",
            "title": "PR",
            "pull_request": {"url": "x"},
        }
        self.assertIsNone(verify_open_issue(opportunity(), fetcher=lambda _: json.dumps(payload).encode()))

    def test_api_failure_fails_closed_and_counts_rejection(self) -> None:
        verified, rejected = verify_open_issues(
            [opportunity(), opportunity("https://github.com/other/repo/issues/9")],
            fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("offline")),
        )
        self.assertEqual(verified, [])
        self.assertEqual(rejected, 2)


if __name__ == "__main__":
    unittest.main()
