from __future__ import annotations

import unittest

from atlas.browser_executor import _validate_url


class BrowserExecutorSafetyTests(unittest.TestCase):
    def test_allows_authorized_https_hosts(self) -> None:
        self.assertEqual(
            _validate_url("https://app.manic.trade/pm"),
            "https://app.manic.trade/pm",
        )
        self.assertEqual(
            _validate_url("https://polymarket.com/event/example"),
            "https://polymarket.com/event/example",
        )

    def test_rejects_non_https_and_unknown_hosts(self) -> None:
        with self.assertRaises(ValueError):
            _validate_url("http://app.manic.trade/pm")
        with self.assertRaises(ValueError):
            _validate_url("https://example.com/")


if __name__ == "__main__":
    unittest.main()
