from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "atlas"))
sys.path.insert(0, str(ROOT / "scripts"))

import moltjobs_cash_sniper as sniper  # noqa: E402


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def job(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "job-1",
        "title": "Summarize a public product brief",
        "status": "OPEN",
        "budgetUsdc": 8,
        "deadlineAt": "2026-08-26T12:00:00Z",
        "paymentProvider": "ON_CHAIN_USDC",
        "paymentStatus": "ESCROWED",
        "acceptanceCriteria": [
            {"description": "Return valid JSON"},
            {"description": "Stay below 200 words"},
        ],
        "inputData": {"generalDescription": "Produce a concise JSON summary."},
    }
    value.update(overrides)
    return value


class MoltJobsCashSniperTests(unittest.TestCase):
    def test_prefers_objective_bounded_paid_work(self) -> None:
        score = sniper.score_job(job(), NOW, {"mode": "quick_win_cash_first"})
        self.assertIsNotNone(score)
        self.assertGreater(score or 0, 100)

    def test_rejects_referral_and_third_party_funding_dependency(self) -> None:
        candidate = job(
            title="Bring a job poster who funds real escrow",
            inputData={"generalDescription": "Recruit another person and ask them to fund 10 USDC."},
        )
        self.assertTrue(sniper.requires_human_dependency(candidate))
        self.assertIsNone(sniper.score_job(candidate, NOW, {"mode": "quick_win_cash_first"}))

    def test_rejects_wallet_signature_or_upfront_spend(self) -> None:
        candidate = job(
            title="Complete a wallet task",
            inputData={"generalDescription": "Connect wallet, sign a transaction, then make a deposit."},
        )
        self.assertTrue(sniper.requires_human_dependency(candidate))
        self.assertIsNone(sniper.score_job(candidate, NOW, {"mode": "quick_win_cash_first"}))

    def test_allows_copywriting_about_outreach_without_sending_it(self) -> None:
        candidate = job(
            title="Write an outreach message",
            inputData={"generalDescription": "Return JSON with initial, followup and dm copy. Do not contact anyone."},
        )
        self.assertFalse(sniper.requires_human_dependency(candidate))
        self.assertIsNotNone(sniper.score_job(candidate, NOW, {"mode": "quick_win_cash_first"}))


if __name__ == "__main__":
    unittest.main()
