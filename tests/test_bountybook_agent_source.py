from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from atlas.bountybook_agent_source import BountyBookAgentJobsSource, _fetch_public_json


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def job(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "job-123",
        "status": "open",
        "title": "Convert JSON records to CSV",
        "budget_usdc": "4.50",
        "spec": {"instructions": "Return a deterministic converter and tests."},
        "deadline": "2026-08-11T12:00:00Z",
        "escrow_status": "funded",
    }
    value.update(overrides)
    return value


def fetcher_for(*jobs: object):
    def fetcher(url: str) -> bytes:
        assert url.startswith("https://api.bountybook.ai/jobs?")
        return json.dumps({"jobs": list(jobs)}).encode("utf-8")

    return fetcher


class BountyBookAgentJobsSourceTests(unittest.TestCase):
    def source(self, *jobs: object) -> BountyBookAgentJobsSource:
        return BountyBookAgentJobsSource(fetcher=fetcher_for(*jobs), now=lambda: NOW)

    def test_collects_open_prefunded_job_without_enabling_claim_or_spend(self) -> None:
        rows, state = self.source(job()).collect()

        self.assertEqual(state.status, "ok")
        self.assertEqual(state.observed_count, 1)
        opportunity = rows[0]
        self.assertEqual(opportunity.currency, "USDC")
        self.assertEqual(opportunity.reward_amount, 4.5)
        self.assertTrue(opportunity.reward_verified)
        self.assertEqual(opportunity.required_capabilities, ("python_automation_delivery",))
        self.assertTrue(opportunity.metadata["claim_is_free"])
        self.assertFalse(opportunity.metadata["autonomous_claim_enabled"])
        self.assertFalse(opportunity.metadata["financial_transaction_signing_enabled"])
        self.assertFalse(opportunity.metadata["spend_authorized"])

    def test_rejects_expired_job_even_when_status_is_open(self) -> None:
        rows, state = self.source(job(deadline="2026-08-08T12:00:00Z")).collect()

        self.assertEqual(rows, [])
        self.assertIn("expired=1", state.reason)

    def test_rejects_explicitly_unfunded_job(self) -> None:
        rows, state = self.source(job(escrow_status="pending_funding")).collect()

        self.assertEqual(rows, [])
        self.assertIn("payment_unverified=1", state.reason)

    def test_rejects_unsafe_account_manipulation(self) -> None:
        rows, state = self.source(job(spec={"instructions": "Use your X account to send DMs."})).collect()

        self.assertEqual(rows, [])
        self.assertIn("unsafe=1", state.reason)

    def test_malformed_envelope_fails_causally(self) -> None:
        source = BountyBookAgentJobsSource(fetcher=lambda _: b'{"data": {}}', now=lambda: NOW)

        rows, state = source.collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("jobs must be a list", state.reason)

    def test_network_fetcher_rejects_other_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "only permits"):
            _fetch_public_json("https://example.com/jobs", timeout_seconds=1, maximum_bytes=100)


if __name__ == "__main__":
    unittest.main()
