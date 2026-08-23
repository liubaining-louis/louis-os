from __future__ import annotations

import unittest

from atlas.external_outcome_reconciliation import (
    apply_summary_to_ledger,
    github_comments_api_url,
    reconcile_receipts,
    wallet_settlement_view,
)


WALLET = "RTC822282d5ce983c4084ad76c724b466c7d92dc1f9"


class ExternalOutcomeReconciliationTests(unittest.TestCase):
    def receipt(self, issue: int) -> dict:
        return {
            "action_id": f"rustchain-{issue}-email-fallback-20260815",
            "candidate_id": f"rustchain-bounty-{issue}",
            "target_url": f"https://github.com/Scottcjn/rustchain-bounties/issues/{issue}",
            "payout_wallet": WALLET,
            "claimed_reward_rtc": 3.0,
            "verified": True,
            "counterparty_review_status": "pending",
            "revenue_confirmed_eur": 0.0,
        }

    def comment(self, body: str, comment_id: int, *, author: str = "Scottcjn") -> dict:
        return {
            "body": body,
            "created_at": "2026-08-22T21:42:39Z",
            "html_url": f"https://github.com/example/issues/1#issuecomment-{comment_id}",
            "user": {"login": author},
        }

    def test_builds_only_the_canonical_public_comments_api(self) -> None:
        self.assertEqual(
            github_comments_api_url("https://github.com/Scottcjn/rustchain-bounties/issues/12442"),
            "https://api.github.com/repos/Scottcjn/rustchain-bounties/issues/12442/comments?per_page=100",
        )
        self.assertIsNone(github_comments_api_url("https://github.com/other/repo/issues/1"))

    def test_reconciles_two_authoritative_queued_payouts(self) -> None:
        first = self.receipt(12442)
        second = self.receipt(12444)
        comments = {
            first["target_url"]: [
                self.comment(
                    "**Payout queued — 3 RTC** to Louis OS (`RTC822282d5…c1f9`). "
                    "pending_id 4050, tx `04265fee4c7b413188d66114c6740a37`.\n\n"
                    "Two-phase: queued now, confirms automatically ~**2026-08-23 21:41 UTC** unless voided; balance moves then.",
                    5382750606,
                )
            ],
            second["target_url"]: [
                self.comment(
                    "**Payouts queued — 3 RTC each, both accepted per-writer.**\n"
                    f"- Louis OS → `{WALLET}`, pending_id 4046, tx `b3a5c4270781bd4fbd860d77a3458af4`\n\n"
                    "Two-phase: queued now, confirms automatically ~**2026-08-23 21:41 UTC** unless voided.",
                    5382750346,
                )
            ],
        }
        payload, summary = reconcile_receipts(
            {"receipts": [first, second]},
            comments_by_target=comments,
            wallet_balances_rtc={WALLET: 0.0},
            checked_at="2026-08-23T17:00:00+00:00",
        )
        self.assertEqual(summary["accepted_count"], 2)
        self.assertEqual(summary["payout_queued_count"], 2)
        self.assertEqual(summary["payout_queued_rtc"], 6.0)
        self.assertEqual(payload["receipts"][0]["payout_pending_id"], "4050")
        self.assertEqual(payload["receipts"][1]["payout_pending_id"], "4046")
        self.assertEqual(payload["receipts"][0]["counterparty_review_status"], "accepted_payout_queued")

    def test_untrusted_payout_comment_is_ignored(self) -> None:
        receipt = self.receipt(12442)
        _, summary = reconcile_receipts(
            {"receipts": [receipt]},
            comments_by_target={
                receipt["target_url"]: [
                    self.comment(f"Payout confirmed to Louis OS {WALLET}", 1, author="random-user")
                ]
            },
            wallet_balances_rtc={WALLET: 0.0},
            checked_at="2026-08-23T17:00:00+00:00",
        )
        self.assertEqual(summary["accepted_count"], 0)

    def test_ledger_records_acceptance_but_not_eur_payment(self) -> None:
        summary = {
            "accepted_count": 2,
            "payout_queued_count": 2,
            "payout_paid_count": 0,
            "payout_queued_rtc": 6.0,
            "wallet_balances_rtc": {WALLET: 0.0},
        }
        result = apply_summary_to_ledger(
            {"qualified_replies": 0, "conversions": 0, "revenue_confirmed_eur": 0.0, "revenue_received": 0.0},
            summary,
            checked_at="2026-08-23T17:00:00+00:00",
        )
        self.assertEqual(result["qualified_replies"], 2)
        self.assertEqual(result["conversions"], 2)
        self.assertEqual(result["missions_won_verified"], 2)
        self.assertEqual(result["payouts_queued"], 2)
        self.assertFalse(result["crypto_payment_verified"])
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)

    def test_wallet_balance_closes_crypto_but_not_eur_transition(self) -> None:
        summary = {
            "accepted_count": 2,
            "payout_queued_count": 2,
            "payout_paid_count": 0,
            "payout_queued_rtc": 6.0,
            "wallet_balances_rtc": {WALLET: 6.0},
        }
        result = apply_summary_to_ledger(
            {
                "last_external_wallet_balance_rtc": 0.0,
                "revenue_confirmed_eur": 0.0,
                "revenue_received": 0.0,
            },
            summary,
            checked_at="2026-08-23T21:45:00+00:00",
        )
        self.assertEqual(result["revenue_received_rtc"], 6.0)
        self.assertEqual(result["payouts_received_verified"], 2)
        self.assertTrue(result["crypto_payment_verified"])
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)
        self.assertEqual(result["revenue_received"], 0.0)

    def test_wallet_settlement_view_exposes_aggregate_receipt(self) -> None:
        summary = {
            "payout_queued_count": 3,
            "payout_queued_rtc": 11.0,
            "wallet_balances_rtc": {WALLET: 11.0},
        }
        view = wallet_settlement_view({"last_external_wallet_balance_rtc": 0.0}, summary)
        self.assertEqual(view["wallet_received_rtc"], 11.0)
        self.assertTrue(view["aggregate_wallet_settlement_verified"])

    def test_paid_comment_still_reconciles_against_wallet(self) -> None:
        summary = {
            "accepted_count": 1,
            "payout_queued_count": 0,
            "payout_paid_count": 1,
            "payout_queued_rtc": 0.0,
            "payout_paid_rtc": 5.0,
            "payout_expected_count": 1,
            "payout_expected_rtc": 5.0,
            "wallet_balances_rtc": {WALLET: 5.0},
        }
        result = apply_summary_to_ledger(
            {"last_external_wallet_balance_rtc": 0.0, "revenue_confirmed_eur": 0.0},
            summary,
            checked_at="2026-08-23T21:45:00+00:00",
        )
        self.assertEqual(result["payouts_queued"], 0)
        self.assertEqual(result["payouts_paid_by_counterparty_receipt"], 1)
        self.assertTrue(result["crypto_payment_verified"])

    def test_later_void_is_not_hidden_by_unless_voided_notice(self) -> None:
        receipt = self.receipt(12442)
        _, summary = reconcile_receipts(
            {"receipts": [receipt]},
            comments_by_target={
                receipt["target_url"]: [
                    self.comment(
                        f"Payout queued — 3 RTC to Louis OS {WALLET}; confirms unless voided.",
                        1,
                    ),
                    {
                        **self.comment(
                            f"Louis OS {WALLET}: pending_id 4050 payout was voided after review.",
                            2,
                        ),
                        "created_at": "2026-08-23T22:00:00Z",
                    },
                ]
            },
            wallet_balances_rtc={WALLET: 0.0},
            checked_at="2026-08-23T22:01:00+00:00",
        )
        self.assertEqual(summary["accepted_count"], 0)
        self.assertEqual(summary["payout_queued_count"], 0)


if __name__ == "__main__":
    unittest.main()
