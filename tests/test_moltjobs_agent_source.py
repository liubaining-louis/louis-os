from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from atlas.moltjobs_agent_source import MoltJobsAgentJobsSource, _fetch_public_json


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def job(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "job-123",
        "status": "OPEN",
        "templateId": "research-v1",
        "title": "Research three API providers",
        "budgetUsdc": "25.50",
        "inputData": {"generalDescription": "Compare documented features and provide cited findings."},
        "acceptanceCriteria": [{"description": "At least three primary sources"}],
        "deadlineAt": "2026-08-11T12:00:00Z",
        "paymentProvider": "ON_CHAIN_USDC",
        "paymentStatus": None,
        "escrowTxHash": None,
        "escrowJobId": None,
    }
    value.update(overrides)
    return value


def fetcher_for(*jobs: object):
    def fetcher(url: str) -> bytes:
        assert url.startswith("https://api.moltjobs.io/v1/jobs?")
        return json.dumps({"data": list(jobs), "meta": {"nextCursor": None}}).encode("utf-8")

    return fetcher


class MoltJobsAgentJobsSourceTests(unittest.TestCase):
    def source(self, *jobs: object) -> MoltJobsAgentJobsSource:
        return MoltJobsAgentJobsSource(fetcher=fetcher_for(*jobs), now=lambda: NOW)

    def test_collects_fresh_on_chain_usdc_job(self) -> None:
        rows, state = self.source(job()).collect()

        self.assertEqual(state.status, "ok")
        self.assertEqual(state.observed_count, 1)
        self.assertEqual(len(rows), 1)
        opportunity = rows[0]
        self.assertEqual(opportunity.currency, "USDC")
        self.assertEqual(opportunity.reward_amount, 25.5)
        self.assertTrue(opportunity.reward_verified)
        self.assertEqual(opportunity.required_capabilities, ("evidence_research_dossier",))
        self.assertTrue(opportunity.account_required)
        self.assertTrue(opportunity.terms_required)
        self.assertFalse(opportunity.metadata["autonomous_bid_enabled"])
        self.assertFalse(opportunity.metadata["paid_bid_credit_purchase_authorized"])

    def test_rejects_expired_job_even_when_api_marks_it_open(self) -> None:
        rows, state = self.source(job(deadlineAt="2026-08-04T12:00:00Z")).collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "empty")
        self.assertIn("expired=1", state.reason)

    def test_rejects_pending_card_authorization_as_unverified_payment(self) -> None:
        rows, state = self.source(
            job(paymentProvider="STRIPE", paymentStatus="PENDING_AUTH")
        ).collect()

        self.assertEqual(rows, [])
        self.assertIn("payment_unverified=1", state.reason)

    def test_accepts_funded_card_payment_state(self) -> None:
        rows, _ = self.source(
            job(paymentProvider="STRIPE", paymentStatus="CAPTURED")
        ).collect()

        self.assertEqual(len(rows), 1)

    def test_rejects_unsafe_or_account_manipulation_work(self) -> None:
        rows, state = self.source(
            job(inputData={"generalDescription": "Use your Instagram account to send DMs to users."})
        ).collect()

        self.assertEqual(rows, [])
        self.assertIn("unsafe=1", state.reason)

    def test_malformed_envelope_fails_with_causal_state(self) -> None:
        source = MoltJobsAgentJobsSource(fetcher=lambda _: b'{"data": {}}', now=lambda: NOW)

        rows, state = source.collect()

        self.assertEqual(rows, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("response data must be a list", state.reason)

    def test_network_fetcher_rejects_any_other_host_before_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "only permits"):
            _fetch_public_json(
                "https://example.com/v1/jobs?status=OPEN",
                timeout_seconds=1,
                maximum_bytes=100,
            )


if __name__ == "__main__":
    unittest.main()
