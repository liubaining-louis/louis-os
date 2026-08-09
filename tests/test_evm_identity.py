from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from atlas.evm_identity import ensure_agentpact_offer, ensure_agentpact_registration, ensure_base_wallet


AGENT_ID = "e94bfedc-d1e7-4814-a157-ea8f750a4acc"


class EvmIdentityTests(unittest.TestCase):
    def test_base_wallet_is_stable_and_private_key_never_enters_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets = root / "secrets"
            results = root / "results"

            first = ensure_base_wallet(secrets, results)
            second = ensure_base_wallet(secrets, results)

            self.assertEqual(first["address"], second["address"])
            self.assertEqual(first["chain_id"], 8453)
            self.assertTrue(first["receive_enabled"])
            self.assertFalse(first["financial_transaction_signing_enabled"])
            self.assertFalse(first["spend_authorized"])
            self.assertEqual(os.stat(secrets / "base-evm-private-key").st_mode & 0o777, 0o600)
            public_text = (results / "base_wallet_public.json").read_text(encoding="utf-8")
            private_text = (secrets / "base-evm-private-key").read_text(encoding="utf-8").strip()
            self.assertNotIn(private_text, public_text)

    def test_agentpact_registration_stores_api_key_only_in_secret_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets = root / "secrets"
            results = root / "results"
            wallet = ensure_base_wallet(secrets, results)
            calls: list[dict[str, object]] = []

            def poster(url: str, body: bytes, headers: dict[str, str]) -> bytes:
                calls.append({"url": url, "body": json.loads(body), "headers": headers})
                return json.dumps({"apiKey": "ap_secret_test", "agentId": AGENT_ID}).encode("utf-8")

            identity = ensure_agentpact_registration(
                secrets,
                results,
                wallet_address=wallet["address"],
                preferred_agent_id=AGENT_ID,
                poster=poster,
            )
            again = ensure_agentpact_registration(
                secrets,
                results,
                wallet_address=wallet["address"],
                preferred_agent_id=AGENT_ID,
                poster=poster,
            )

            self.assertEqual(identity["agent_id"], AGENT_ID)
            self.assertEqual(again["status"], "registered")
            self.assertEqual(len(calls), 1)
            self.assertEqual(os.stat(secrets / "agentpact-api-key").st_mode & 0o777, 0o600)
            result_text = "".join(path.read_text(encoding="utf-8") for path in results.glob("*.json"))
            self.assertNotIn("ap_secret_test", result_text)

    def test_agentpact_offer_is_published_once_and_requires_no_spend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets = root / "secrets"
            results = root / "results"
            wallet = ensure_base_wallet(secrets, results)

            def register_poster(url: str, body: bytes, headers: dict[str, str]) -> bytes:
                return json.dumps({"apiKey": "ap_secret_test", "agentId": AGENT_ID}).encode("utf-8")

            ensure_agentpact_registration(
                secrets,
                results,
                wallet_address=wallet["address"],
                preferred_agent_id=AGENT_ID,
                poster=register_poster,
            )
            calls: list[dict[str, object]] = []

            def offer_poster(url: str, body: bytes, headers: dict[str, str]) -> bytes:
                calls.append({"url": url, "body": json.loads(body), "headers": headers})
                return b'{"offer":{"id":"offer-123"}}'

            first = ensure_agentpact_offer(secrets, results, agent_id=AGENT_ID, poster=offer_poster)
            second = ensure_agentpact_offer(secrets, results, agent_id=AGENT_ID, poster=offer_poster)

            self.assertEqual(first["offer_id"], "offer-123")
            self.assertEqual(second["offer_id"], "offer-123")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["headers"]["x-api-key"], "ap_secret_test")
            self.assertFalse(first["work_before_escrow_enabled"])
            self.assertFalse(first["financial_transaction_signing_enabled"])


if __name__ == "__main__":
    unittest.main()
