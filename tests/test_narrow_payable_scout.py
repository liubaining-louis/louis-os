from __future__ import annotations

import unittest

from atlas.narrow_payable_scout import (
    detect_provider_evidence,
    discover_narrow_payable_registry,
)


def issue(
    number: int,
    *,
    title: str = "Fix a documentation typo",
    body: str = 'In file `docs/guide.md` replace "teh" with "the".',
    labels: list[str] | None = None,
) -> dict:
    return {
        "html_url": f"https://github.com/example/project/issues/{number}",
        "url": f"https://api.github.com/repos/example/project/issues/{number}",
        "repository_url": "https://api.github.com/repos/example/project",
        "comments_url": f"https://api.github.com/repos/example/project/issues/{number}/comments",
        "number": number,
        "title": title,
        "body": body,
        "state": "open",
        "updated_at": "2026-07-26T18:00:00Z",
        "labels": [{"name": name} for name in (labels or ["good first issue", "documentation", "💎 Bounty"])],
        "assignees": [],
    }


def algora_comment(number: int, amount: int = 75, *, struck: bool = False) -> dict:
    heading = "~~## 💎" if struck else "## 💎"
    return {
        "html_url": f"https://github.com/example/project/issues/{number}#issuecomment-1",
        "user": {"login": "algora-pbc[bot]"},
        "body": (
            f"{heading} ${amount} bounty • Example\n\n"
            f"1. Start working: Comment `/attempt #{number}` with your implementation plan\n"
            f"2. Submit work: Create a pull request including `/claim #{number}` in the PR body\n"
            "3. Receive payment: 100% of the bounty is received post-reward."
        ),
    }


class NarrowPayableScoutTests(unittest.TestCase):
    def getter_for(self, items: list[dict], comments: dict[int, list[dict]]):
        def getter(url: str):
            if "/search/issues?" in url:
                return {"items": items}
            if "/comments" in url:
                number = int(url.split("/issues/", 1)[1].split("/", 1)[0])
                return comments.get(number, [])
            if url == "https://api.github.com/repos/example/project":
                return {"full_name": "example/project", "archived": False, "disabled": False}
            raise AssertionError(f"unexpected URL: {url}")
        return getter

    def test_algora_provider_evidence_is_required_and_parsed(self) -> None:
        evidence = detect_provider_evidence([algora_comment(1, 125)])
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.provider, "algora")
        self.assertEqual(evidence.reward_amount, 125)
        self.assertEqual(evidence.currency, "USD")

    def test_narrow_platform_backed_task_qualifies(self) -> None:
        item = issue(1)
        outcome = discover_narrow_payable_registry(
            getter=self.getter_for([item], {1: [algora_comment(1)]}),
            queries=("one-query",),
            max_candidates=3,
        )
        self.assertEqual(outcome.inspected, 1)
        self.assertEqual(outcome.qualified, 1)
        candidate = outcome.registry["candidates"][0]
        self.assertTrue(candidate["credible_payable"])
        self.assertEqual(candidate["payment_provider"], "algora")
        self.assertEqual(candidate["patch_handler"], "deterministic_text_replacement")
        self.assertEqual(candidate["readiness_status"], "executable_now")
        self.assertFalse(candidate["requires_user_validation"])
        self.assertGreater(candidate["reward_scope_ratio"], 0)

    def test_issue_money_without_provider_bot_is_rejected(self) -> None:
        item = issue(2, title="$500 bounty", body='In file `README.md` replace "old" with "new".')
        outcome = discover_narrow_payable_registry(
            getter=self.getter_for([item], {2: []}),
            queries=("one-query",),
        )
        self.assertEqual(outcome.qualified, 0)
        self.assertEqual(outcome.rejected[0]["reason"], "recognized_provider_evidence_missing")

    def test_rewarded_or_struck_bounty_is_rejected(self) -> None:
        rewarded = issue(3, labels=["good first issue", "documentation", "💎 Bounty", "💰 Rewarded"])
        struck = issue(4)
        outcome = discover_narrow_payable_registry(
            getter=self.getter_for(
                [rewarded, struck],
                {3: [algora_comment(3)], 4: [algora_comment(4, struck=True)]},
            ),
            queries=("one-query",),
        )
        reasons = {item["reason"] for item in outcome.rejected}
        self.assertIn("already_rewarded", reasons)
        self.assertIn("provider_bounty_struck_or_cancelled", reasons)
        self.assertEqual(outcome.qualified, 0)

    def test_broad_task_is_not_promoted(self) -> None:
        broad = issue(
            5,
            title="Full implementation and architecture overhaul",
            body=(
                "Implement in full the entire codebase migration, all main components, "
                "a large refactor, 20,000 lines and 100+ files."
            ),
            labels=["💎 Bounty"],
        )
        outcome = discover_narrow_payable_registry(
            getter=self.getter_for([broad], {5: [algora_comment(5, 500)]}),
            queries=("one-query",),
        )
        self.assertEqual(outcome.qualified, 0)
        self.assertEqual(outcome.rejected[0]["reason"], "task_not_narrow_enough")

    def test_supported_patch_is_ranked_before_unsupported_higher_reward(self) -> None:
        supported = issue(6)
        unsupported = issue(
            7,
            title="Small API improvement",
            body="Add one small API improvement with acceptance tests.",
            labels=["good first issue", "💎 Bounty"],
        )
        outcome = discover_narrow_payable_registry(
            getter=self.getter_for(
                [unsupported, supported],
                {6: [algora_comment(6, 50)], 7: [algora_comment(7, 500)]},
            ),
            queries=("one-query",),
            max_candidates=5,
        )
        self.assertTrue(outcome.registry["candidates"][0]["url"].endswith("/6"))
        self.assertEqual(outcome.registry["candidates"][0]["patch_handler"], "deterministic_text_replacement")


if __name__ == "__main__":
    unittest.main()
