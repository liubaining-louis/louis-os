from __future__ import annotations

import unittest

from atlas.payable_source_adapters import detect_payment_evidence


class PayableSourceAdapterTests(unittest.TestCase):
    def test_recognized_algora_bot_is_accepted(self) -> None:
        evidence = detect_payment_evidence(
            [
                {
                    "html_url": "https://github.com/acme/docs/issues/1#issuecomment-1",
                    "user": {"login": "algora-pbc[bot]"},
                    "body": "## 💎 $75 bounty\n/attempt #1 then /claim #1 and receive payment.",
                }
            ]
        )
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.provider, "algora")
        self.assertEqual(evidence.evidence_type, "recognized_provider_bot")
        self.assertEqual(evidence.reward_amount, 75)

    def test_maintainer_attested_platform_link_is_accepted(self) -> None:
        evidence = detect_payment_evidence(
            [
                {
                    "html_url": "https://github.com/acme/docs/issues/2#issuecomment-2",
                    "user": {"login": "acme-maintainer"},
                    "author_association": "OWNER",
                    "body": "Official $120 reward and claim page: https://polar.sh/acme/rewards/2",
                }
            ]
        )
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.provider, "polar")
        self.assertEqual(evidence.evidence_type, "maintainer_attested_platform_link")
        self.assertEqual(evidence.currency, "USD")

    def test_untrusted_user_platform_link_is_rejected(self) -> None:
        evidence = detect_payment_evidence(
            [
                {
                    "html_url": "https://github.com/acme/docs/issues/3#issuecomment-3",
                    "user": {"login": "random-user"},
                    "author_association": "NONE",
                    "body": "Claim a $500 bounty at https://gitcoin.co/bounty/3",
                }
            ]
        )
        self.assertIsNone(evidence)

    def test_money_without_comment_evidence_is_rejected(self) -> None:
        self.assertIsNone(detect_payment_evidence([]))


if __name__ == "__main__":
    unittest.main()
