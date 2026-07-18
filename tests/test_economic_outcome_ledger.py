from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.economic_outcome_ledger import EconomicOutcome, EconomicOutcomeLedger


def outcome(index: int, stage: str, **overrides) -> EconomicOutcome:
    values = {
        "outcome_id": f"o{index}",
        "experiment_id": "exp-1",
        "prospect_id": f"p{index}",
        "stage": stage,
        "revenue": 0.0,
        "variable_cost": 0.0,
        "fixed_cost_allocated": 0.0,
        "conversion_probability": 0.0,
        "currency": "EUR",
    }
    values.update(overrides)
    return EconomicOutcome(**values)


class EconomicOutcomeLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = EconomicOutcomeLedger(minimum_observations=5)

    def test_continues_when_sample_is_too_small(self):
        result = self.ledger.summarize("exp-1", [outcome(1, "lead", conversion_probability=0.2)])
        self.assertEqual(result.decision, "continue")

    def test_accelerates_profitable_converting_experiment(self):
        items = [
            outcome(1, "quote", revenue=10000, variable_cost=6000, conversion_probability=0.5),
            outcome(2, "order", revenue=10000, variable_cost=6000, conversion_probability=1.0),
            outcome(3, "lead", revenue=5000, variable_cost=3000, conversion_probability=0.2),
            outcome(4, "lost"),
            outcome(5, "lost"),
        ]
        result = self.ledger.summarize("exp-1", items)
        self.assertEqual(result.decision, "accelerate")
        self.assertEqual(result.booked_revenue, 10000)
        self.assertEqual(result.booked_gross_profit, 4000)
        self.assertEqual(result.quote_to_order_rate, 1.0)

    def test_stops_non_viable_experiment_without_revenue(self):
        items = [
            outcome(1, "quote", revenue=1000, variable_cost=1200, conversion_probability=0.5),
            outcome(2, "lost"), outcome(3, "lost"), outcome(4, "lost"), outcome(5, "lost")
        ]
        result = self.ledger.summarize("exp-1", items)
        self.assertEqual(result.decision, "stop")

    def test_revises_low_margin_booked_business(self):
        items = [
            outcome(1, "quote", revenue=1000, variable_cost=900, conversion_probability=0.5),
            outcome(2, "order", revenue=1000, variable_cost=900, conversion_probability=1.0),
            outcome(3, "lead"), outcome(4, "lost"), outcome(5, "lost")
        ]
        result = self.ledger.summarize("exp-1", items)
        self.assertEqual(result.decision, "revise")

    def test_rejects_duplicate_ids_and_mixed_currency(self):
        with self.assertRaises(ValueError):
            self.ledger.summarize("exp-1", [outcome(1, "lead"), outcome(1, "lost")])
        with self.assertRaises(ValueError):
            self.ledger.summarize("exp-1", [outcome(1, "lead"), outcome(2, "lead", currency="USD")])

    def test_rejects_invalid_order_and_wrong_experiment(self):
        with self.assertRaises(ValueError):
            self.ledger.summarize("exp-1", [outcome(1, "order")])
        with self.assertRaises(ValueError):
            self.ledger.summarize("exp-1", [
                EconomicOutcome("o1", "other", "p1", "lead")
            ])

    def test_writes_auditable_artifact(self):
        result = self.ledger.summarize("exp-1", [
            outcome(1, "lead"), outcome(2, "lead"), outcome(3, "lost"), outcome(4, "lost"), outcome(5, "lost")
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            self.ledger.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["economic_outcome"]["experiment_id"], "exp-1")


if __name__ == "__main__":
    unittest.main()
