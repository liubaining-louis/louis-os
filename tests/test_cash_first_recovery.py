from __future__ import annotations

from datetime import datetime, timezone
import unittest

from atlas.cash_first_recovery import build_recovery_payload, recovery_candidates, source_metrics


class CashFirstRecoveryTests(unittest.TestCase):
    def history_item(self, **overrides):
        value = {
            "opportunity_id": "opp-1",
            "title": "English to French product translation",
            "source_id": "freelancer_public_simple_jobs",
            "source_url": "https://example.test/opp-1",
            "first_seen_at": "2026-07-25T08:00:00+00:00",
            "last_seen_at": "2026-07-27T08:00:00+00:00",
            "lifecycle_status": "prepared",
            "active_in_latest_cycle": False,
            "latest": {
                "reward_amount": 120.0,
                "currency": "USD",
                "time_to_cash_days": 14,
                "competition": 0.2,
                "required_capabilities": ["translation_delivery"],
                "metadata": {"estimated_effort_hours": 8.0},
                "decision": {"status": "prepare_then_gate", "blockers": ["account_required"]},
            },
        }
        value.update(overrides)
        return value

    def test_recovers_recent_prepared_opportunity_but_requires_revalidation(self) -> None:
        rows = recovery_candidates(
            [self.history_item()],
            now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["revalidation_required"])
        self.assertFalse(rows[0]["submission_allowed"])
        self.assertEqual(rows[0]["action"], "revalidate_canonical_listing_before_restoring_to_cash_first")

    def test_does_not_recover_terminal_or_stale_items(self) -> None:
        submitted = self.history_item(opportunity_id="submitted", lifecycle_status="submitted")
        stale = self.history_item(opportunity_id="stale", last_seen_at="2026-06-01T08:00:00+00:00")
        rows = recovery_candidates(
            [submitted, stale],
            now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])

    def test_source_metrics_reward_prepared_yield(self) -> None:
        items = [
            self.history_item(opportunity_id="a", lifecycle_status="prepared"),
            self.history_item(opportunity_id="b", lifecycle_status="executable"),
            self.history_item(opportunity_id="c", lifecycle_status="rejected"),
        ]
        metrics = source_metrics(items)
        self.assertEqual(metrics[0]["source_id"], "freelancer_public_simple_jobs")
        self.assertEqual(metrics[0]["prepared_or_better"], 2)
        self.assertGreater(metrics[0]["allocation_score"], 40)

    def test_payload_generates_capability_reuse_and_truth_guards(self) -> None:
        current = {
            "opportunities": [
                {
                    "title": "Native Thai voice recording",
                    "decision": {"status": "rejected", "blockers": ["unverifiable_personal_eligibility"]},
                    "metadata": {"policy_rejection": "unverifiable_personal_eligibility"},
                }
            ]
        }
        history = {"items": [self.history_item()]}
        payload = build_recovery_payload(
            current,
            history,
            now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["counts"]["recovery_candidates"], 1)
        self.assertTrue(any(item.get("capability_id") == "translation_delivery" for item in payload["search_directives"]))
        self.assertTrue(payload["truth"]["canonical_revalidation_required"])
        self.assertEqual(payload["truth"]["external_submissions_verified"], 0)
        self.assertEqual(payload["truth"]["revenue_verified_eur"], 0.0)


if __name__ == "__main__":
    unittest.main()
