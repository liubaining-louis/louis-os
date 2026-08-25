from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "atlas"))
sys.path.insert(0, str(ROOT / "scripts"))

import taskforce_cash_sniper as sniper  # noqa: E402

POLICY = json.loads((ROOT / "config" / "production_policy.json").read_text(encoding="utf-8"))


def task(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "task-1",
        "title": "Automate a CSV validation report",
        "description": "Build a bounded Python script that validates a supplied CSV and returns a concise report.",
        "requirements": "Include deterministic tests and usage instructions.",
        "category": "development",
        "totalBudget": 100,
        "estimatedEffortHours": 2,
        "applicationCount": 2,
        "deadline": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "skillsRequired": ["python", "csv"],
    }
    value.update(overrides)
    return value


class TaskForceHigherValueTests(unittest.TestCase):
    def test_accepts_bounded_higher_value_task(self) -> None:
        ok, reason, opportunity = sniper.qualified(task(), POLICY)
        self.assertTrue(ok, reason)
        self.assertEqual(opportunity["reward_amount"], 100)
        self.assertGreater(sniper.execution_score(task()), 0)

    def test_rejects_explicitly_oversized_effort(self) -> None:
        ok, reason, _ = sniper.qualified(task(estimatedEffortHours=8), POLICY)
        self.assertFalse(ok)
        self.assertEqual(reason, "effort_exceeds_three_hours")

    def test_rejects_wallet_or_spend_dependency(self) -> None:
        candidate = task(description="Connect wallet, sign a transaction and deposit funds before delivery.")
        self.assertTrue(sniper.requires_human_dependency(candidate))
        ok, reason, _ = sniper.qualified(candidate, POLICY)
        self.assertFalse(ok)
        self.assertEqual(reason, "human_or_financial_dependency")

    def test_transient_market_statuses_are_retryable(self) -> None:
        self.assertTrue(sniper.is_transient_http_status(429))
        self.assertTrue(sniper.is_transient_http_status(500))
        self.assertFalse(sniper.is_transient_http_status(401))
        self.assertFalse(sniper.is_transient_http_status(404))

    def test_value_density_beats_equal_fit_lower_ticket(self) -> None:
        high = task(totalBudget=100, estimatedEffortHours=2)
        low = task(id="task-2", totalBudget=10, estimatedEffortHours=2)
        self.assertGreater(sniper.execution_score(high), sniper.execution_score(low))


if __name__ == "__main__":
    unittest.main()
