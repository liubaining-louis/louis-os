from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.crypto_revenue import run_crypto_revenue_cycle


class CryptoRevenueTests(unittest.TestCase):
    def test_balance_increase_becomes_on_chain_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "crypto_wallet_public.json").write_text(json.dumps({"address": "WalletAddress"}))
            (results / "platform_accounts.json").write_text(json.dumps({"accounts": {"superteam": {"status": "ready"}}}))
            with patch("atlas.crypto_revenue.read_balances", return_value={"SOL": {"raw": 0, "decimals": 9, "amount": 0.0}}):
                first = run_crypto_revenue_cycle(root)
            self.assertFalse(first["crypto_received"])
            self.assertEqual(first["stage"], "ACCOUNT_READY")
            with patch("atlas.crypto_revenue.read_balances", return_value={"SOL": {"raw": 1_000_000_000, "decimals": 9, "amount": 1.0}}):
                second = run_crypto_revenue_cycle(root)
            self.assertTrue(second["crypto_received"])
            self.assertEqual(second["stage"], "ON_CHAIN_CONFIRMED")
            self.assertEqual(second["received_events"][-1]["amount"], 1.0)

    def test_submission_receipt_maps_to_submitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "crypto_wallet_public.json").write_text(json.dumps({"address": "WalletAddress"}))
            (results / "superteam_submission_receipt.json").write_text(json.dumps({"id": "receipt"}))
            with patch("atlas.crypto_revenue.read_balances", return_value={"SOL": {"raw": 0, "decimals": 9, "amount": 0.0}}):
                out = run_crypto_revenue_cycle(root)
            self.assertEqual(out["stage"], "SUBMITTED")


if __name__ == "__main__":
    unittest.main()
