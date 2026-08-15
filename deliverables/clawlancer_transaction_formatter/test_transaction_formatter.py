import unittest

from transaction_formatter import format_transactions


class TransactionFormatterTests(unittest.TestCase):
    def test_empty_history(self):
        self.assertEqual(format_transactions([]), "_No transactions._")

    def test_formats_common_fields_and_shortens_addresses(self):
        txs = [
            {
                "hash": "0x1234567890abcdef1234567890abcdef",
                "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "to": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "value": "12.50",
                "symbol": "USDC",
                "status": "confirmed",
                "timestamp": 0,
            }
        ]
        table = format_transactions(txs)
        self.assertIn("`0x1234…cdef`", table)
        self.assertIn("`0xaaaa…aaaa`", table)
        self.assertIn("`0xbbbb…bbbb`", table)
        self.assertIn("12.50 USDC", table)
        self.assertIn("confirmed", table)
        self.assertIn("1970-01-01 00:00:00 UTC", table)

    def test_accepts_aliases(self):
        txs = [
            {
                "tx_hash": "abc123",
                "sender": "alice",
                "recipient": "bob",
                "amount": 3,
                "currency": "ETH",
                "created_at": "2026-08-15T06:00:00Z",
            }
        ]
        table = format_transactions(txs)
        self.assertIn("`abc123`", table)
        self.assertIn("`alice`", table)
        self.assertIn("`bob`", table)
        self.assertIn("3 ETH", table)
        self.assertIn("unknown", table)
        self.assertIn("2026-08-15 06:00:00 UTC", table)

    def test_escapes_markdown_and_newlines(self):
        table = format_transactions([{"hash": "x|y", "status": "ok\nnext"}])
        self.assertIn("x\\|y", table)
        self.assertIn("ok next", table)

    def test_rejects_non_mapping_items(self):
        with self.assertRaises(TypeError):
            format_transactions(["not-a-transaction"])


if __name__ == "__main__":
    unittest.main()
