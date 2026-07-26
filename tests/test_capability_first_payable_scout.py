from __future__ import annotations

import unittest

from atlas.capability_first_payable_scout import discover_capability_first_registry


def issue(number: int) -> dict:
    return {
        "html_url": f"https://github.com/acme/docs/issues/{number}",
        "repository_url": "https://api.github.com/repos/acme/docs",
        "comments_url": f"https://api.github.com/repos/acme/docs/issues/{number}/comments",
        "number": number,
        "title": "Fix broken documentation link",
        "body": "In `README.md`, replace https://old.example/docs with https://new.example/docs.",
        "state": "open",
        "updated_at": "2026-07-26T20:00:00Z",
        "labels": [{"name": "good first issue"}, {"name": "documentation"}, {"name": "bounty"}],
        "assignees": [],
    }


def maintainer_payment_comment(number: int, association: str = "OWNER") -> dict:
    return {
        "html_url": f"https://github.com/acme/docs/issues/{number}#issuecomment-1",
        "user": {"login": "acme-maintainer"},
        "author_association": association,
        "body": f"Official $120 bounty claim: https://polar.sh/acme/rewards/{number}",
    }


class CapabilityFirstPayableScoutTests(unittest.TestCase):
    def getter(self, association: str = "OWNER"):
        item = issue(1)

        def get(url: str):
            if "/search/issues?" in url:
                return {"items": [item]}
            if "/comments" in url:
                return [maintainer_payment_comment(1, association)]
            if url == "https://api.github.com/repos/acme/docs":
                return {
                    "full_name": "acme/docs",
                    "archived": False,
                    "disabled": False,
                    "owner": {"type": "Organization"},
                    "stargazers_count": 150,
                    "forks_count": 20,
                    "created_at": "2020-01-01T00:00:00Z",
                    "pushed_at": "2026-07-25T00:00:00Z",
                    "description": "Trusted documentation repository",
                }
            raise AssertionError(f"unexpected URL: {url}")

        return get

    def test_maintainer_attested_reward_and_capability_qualify(self) -> None:
        outcome = discover_capability_first_registry(
            getter=self.getter(),
            queries=("one-query",),
            max_inspected=5,
        )
        self.assertEqual(outcome.qualified, 1)
        candidate = outcome.registry["candidates"][0]
        self.assertEqual(candidate["payment_provider"], "polar")
        self.assertEqual(candidate["payment_evidence_type"], "maintainer_attested_platform_link")
        self.assertEqual(candidate["patch_handler"], "broken_link_replacement")
        self.assertEqual(candidate["readiness_status"], "executable_now")
        self.assertTrue(candidate["current_patch_handler_supported"])

    def test_non_maintainer_platform_link_does_not_qualify(self) -> None:
        outcome = discover_capability_first_registry(
            getter=self.getter("NONE"),
            queries=("one-query",),
            max_inspected=5,
        )
        self.assertEqual(outcome.qualified, 0)
        self.assertEqual(outcome.rejected[0]["reason"], "verified_payment_adapter_evidence_missing")


if __name__ == "__main__":
    unittest.main()
