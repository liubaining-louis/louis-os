from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.crypto_identity import base58_encode, register_platform_account, solana_address_from_spki_der


class CryptoIdentityTests(unittest.TestCase):
    def test_base58_preserves_leading_zeroes(self) -> None:
        self.assertEqual(base58_encode(b"\x00\x00\x01"), "112")

    def test_solana_address_from_ed25519_spki(self) -> None:
        prefix = bytes.fromhex("302a300506032b6570032100")
        raw = bytes(range(32))
        address = solana_address_from_spki_der(prefix + raw)
        self.assertTrue(address)
        self.assertNotIn("0", address)

    def test_platform_registry_never_stores_auth_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            account = register_platform_account(
                results,
                platform="superteam",
                email="optimumanufacturing@gmail.com",
                account_ref="louis-os-agent",
                auth_material_present=True,
            )
            self.assertEqual(account["status"], "ready")
            payload = json.loads((results / "platform_accounts.json").read_text())
            text = json.dumps(payload)
            self.assertNotIn("apiKey", text)
            self.assertFalse(account["secrets_stored_in_registry"])


if __name__ == "__main__":
    unittest.main()
