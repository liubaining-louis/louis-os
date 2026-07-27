from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuruEvidenceContractTests(unittest.TestCase):
    def test_authoritative_source_and_safepay_evidence_are_documented(self) -> None:
        text = (ROOT / "docs/evidence/GURU_PUBLIC_SOURCE.md").read_text(encoding="utf-8")
        self.assertIn("https://www.guru.com/d/jobs/", text)
        self.assertIn("https://www.guru.com/safepay/", text)
        self.assertIn("No account, quote, agreement, KYC, payout setup, submission or revenue", text)


if __name__ == "__main__":
    unittest.main()
