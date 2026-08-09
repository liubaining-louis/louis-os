from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from atlas.agentpact_need_source import AgentPactNeedsSource, _fetch_public_json


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def need(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "need-123",
        "status": "open",
        "title": "JSON to CSV converter",
        "descriptionMd": "Convert nested JSON rows into a validated CSV output.",
        "category": "data",
        "budgetMin": 2,
        "budgetMax": 5,
        "slaDays": 1,
    }
    value.update(overrides)
    return value


def fetcher_for(*needs: object):
    def fetcher(url: str) -> bytes:
        assert url == "https://api.agentpact.xyz/api/needs"
        return json.dumps({"data": {"needs": list(needs)}}).encode("utf-8")

    return fetcher


class AgentPactNeedsSourceTests(unittest.TestCase):
    def source(self, *needs: object) -> AgentPactNeedsSource:
        return AgentPactNeedsSource(fetcher=fetcher_for(*needs), now=lambda: NOW)

    def test_collects_need_as_unfunded_negotiation_lead(self) -> None:
        rows, state = self.source(need()).collect()

        self.assertEqual(state.status, "partial")
        self.assertEqual(state.observed_count, 1)
        opportunity = rows[0]
        self.assertEqual(opportunity.reward_amount, 5)
        self.assertFalse(opportunity.reward_verified)
        self.assertEqual(opportunity.metadata["market_stage"], "unfunded_need")
        self.assertTrue(opportunity.metadata["escrow_required_before_work"])
        self.assertFalse(opportunity.metadata["autonomous_delivery_enabled"])
        self.assertFalse(opportunity.metadata["financial_transaction_signing_enabled"])

    def test_rejects_closed_need(self) -> None:
        rows, state = self.source(need(status="closed")).collect()

        self.assertEqual(rows, [])
        self.assertIn("not_open=1", state.reason)

    def test_rejects_unsafe_need(self) -> None:
        rows, state = self.source(need(descriptionMd="Create malware and steal credentials.")).collect()

        self.assertEqual(rows, [])
        self.assertIn("unsafe=1", state.reason)

    def test_malformed_envelope_fails_causally(self) -> None:
        source = AgentPactNeedsSource(fetcher=lambda _: b'{"data": {}}', now=lambda: NOW)

        rows, state = source.collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("needs must be a list", state.reason)

    def test_network_fetcher_rejects_other_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "only permits"):
            _fetch_public_json("https://example.com/api/needs", timeout_seconds=1, maximum_bytes=100)


if __name__ == "__main__":
    unittest.main()
