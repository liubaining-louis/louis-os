from __future__ import annotations

from datetime import datetime, timezone
import unittest

from atlas.superteam_agent_source import SuperteamAgentListingsSource


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def listing(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "listing-123",
        "slug": "agent-api-research",
        "status": "OPEN",
        "agentAccess": "AGENT_ONLY",
        "title": "Research agent API providers",
        "description": "Compare official API documentation with citations.",
        "rewardAmount": 25,
        "rewardCurrency": "USDC",
        "deadline": "2026-08-11T12:00:00Z",
        "isWinnersAnnounced": False,
    }
    value.update(overrides)
    return value


class SuperteamAgentListingsSourceTests(unittest.TestCase):
    def source(self, *items: object, api_key: str = "st_test") -> SuperteamAgentListingsSource:
        return SuperteamAgentListingsSource(
            api_key=api_key,
            fetcher=lambda _: {"listings": list(items)},
            now=lambda: NOW,
        )

    def test_collects_only_agent_eligible_fresh_listing(self) -> None:
        rows, state = self.source(listing()).collect()

        self.assertEqual(state.status, "ok")
        self.assertEqual(state.observed_count, 1)
        self.assertEqual(rows[0].metadata["agent_access"], "AGENT_ONLY")
        self.assertTrue(rows[0].metadata["autonomous_submission_enabled"])
        self.assertFalse(rows[0].metadata["spend_authorized"])

    def test_missing_api_key_is_credential_gated(self) -> None:
        rows, state = self.source(listing(), api_key="").collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "credential_gated")

    def test_rejects_human_only_and_expired_listings(self) -> None:
        rows, state = self.source(
            listing(id="human", slug="human", agentAccess="HUMAN_ONLY"),
            listing(id="expired", slug="expired", deadline="2026-08-08T12:00:00Z"),
        ).collect()

        self.assertEqual(rows, [])
        self.assertIn("agent_ineligible=1", state.reason)
        self.assertIn("expired=1", state.reason)


if __name__ == "__main__":
    unittest.main()
