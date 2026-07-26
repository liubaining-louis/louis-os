import unittest

from atlas.opportunity_authenticity import assess_opportunity_authenticity


def issue(title: str, body: str, **overrides) -> dict:
    value = {
        "title": title,
        "body": body,
        "html_url": "https://github.com/example/project/issues/42",
        "repository_url": "https://api.github.com/repos/example/project",
        "state": "open",
    }
    value.update(overrides)
    return value


class OpportunityAuthenticityTests(unittest.TestCase):
    def test_authoritative_paid_issue_is_verified(self):
        result = assess_opportunity_authenticity(
            issue(
                "$500 bounty: repair the parser",
                "This funded bounty pays $500. Submit a tested pull request with the implementation and acceptance tests.",
            )
        )
        self.assertTrue(result.verified)
        self.assertEqual(result.status, "verified_authoritative_reward")
        self.assertEqual(result.reward_amount, 500)
        self.assertEqual(result.currency, "USD")

    def test_unfunded_bounty_is_rejected(self):
        result = assess_opportunity_authenticity(
            issue("UNFUNDED bounty: parser work", "Potential reward $500. Submit a pull request.")
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.status, "rejected_misleading_or_unfunded")
        self.assertIn("explicitly_unfunded", result.reasons)

    def test_unpaid_prize_complaint_is_not_an_opportunity(self):
        result = assess_opportunity_authenticity(
            issue("Prize payment complaint", "The $10,000 prize was never paid to the winner.")
        )
        self.assertFalse(result.verified)
        self.assertIn("explicitly_unpaid", result.reasons)

    def test_product_price_is_not_interpreted_as_reward(self):
        result = assess_opportunity_authenticity(
            issue("Phone release article", "The phone costs €1,200 at retail and ships next month.")
        )
        self.assertFalse(result.verified)
        self.assertIn("money_appears_in_non_reward_context", result.reasons)
        self.assertIn("no_explicit_reward_amount_binding", result.reasons)

    def test_amount_without_submission_path_is_unverified(self):
        result = assess_opportunity_authenticity(
            issue("Research grant announcement", "A grant reward of 20,000 EUR is discussed in this publication list.")
        )
        self.assertFalse(result.verified)
        self.assertIn("no_official_submission_or_deliverable_path", result.reasons)

    def test_repository_identity_mismatch_fails_closed(self):
        result = assess_opportunity_authenticity(
            issue(
                "$250 bounty",
                "Reward $250. Submit a tested patch.",
                repository_url="https://api.github.com/repos/other/project",
            )
        )
        self.assertFalse(result.verified)
        self.assertIn("repository_identity_mismatch", result.reasons)

    def test_closed_or_claimed_bounty_is_rejected(self):
        result = assess_opportunity_authenticity(
            issue("$300 bounty", "Winner selected. Reward $300 for the submitted solution.")
        )
        self.assertFalse(result.verified)
        self.assertIn("opportunity_closed", result.reasons)

    def test_subjective_fictional_agent_trap_is_rejected(self):
        result = assess_opportunity_authenticity(
            issue(
                "$250 bounty easy task for agents",
                (
                    "Submit a pull request. Payment goes to a celestial Bank Account aboard Space Station 13. "
                    "I reserve the right to refuse payout based on my personal feeling. "
                    "The patch must contain 20,000 lines and 100+ file edits in Ye Olde English."
                ),
                labels=[{"name": "bounty", "description": "for slopbots"}],
            )
        )
        self.assertFalse(result.verified)
        self.assertIn("subjective_or_discretionary_payout", result.reasons)
        self.assertIn("fictional_or_unpayable_reward", result.reasons)
        self.assertIn("adversarial_agent_trap", result.reasons)
        self.assertIn("absurd_scope_requirement", result.reasons)


if __name__ == "__main__":
    unittest.main()
