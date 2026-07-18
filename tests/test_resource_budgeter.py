from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.resource_budgeter import AutonomousResourceBudgeter, ResourceDemand


def demand(**overrides):
    values = {
        "opportunity_id": "opp-1",
        "priority_score": 0.8,
        "requested_attention": 0.6,
        "requested_compute": 0.5,
        "requested_cost": 0.2,
        "evidence_confidence": 0.8,
    }
    values.update(overrides)
    return ResourceDemand(**values)


class AutonomousResourceBudgeterTests(unittest.TestCase):
    def test_allocates_more_to_stronger_evidence_weighted_priority(self) -> None:
        budgeter = AutonomousResourceBudgeter()
        allocations = budgeter.allocate([
            demand(opportunity_id="opp-high", priority_score=0.9, evidence_confidence=0.9),
            demand(opportunity_id="opp-low", priority_score=0.4, evidence_confidence=0.4),
        ])
        by_id = {item.opportunity_id: item for item in allocations}
        self.assertGreater(by_id["opp-high"].attention_budget, by_id["opp-low"].attention_budget)

    def test_defers_low_confidence_demand(self) -> None:
        result = AutonomousResourceBudgeter().allocate([
            demand(evidence_confidence=0.1)
        ])[0]
        self.assertEqual(result.decision, "defer")
        self.assertEqual(result.attention_budget, 0.0)

    def test_throttles_request_above_bounded_share(self) -> None:
        allocations = AutonomousResourceBudgeter(total_cost_budget=0.1).allocate([
            demand(opportunity_id="opp-1", requested_cost=0.9),
            demand(opportunity_id="opp-2", requested_cost=0.9),
        ])
        self.assertTrue(all(item.decision == "throttle" for item in allocations))
        self.assertLessEqual(sum(item.cost_budget for item in allocations), 0.1)

    def test_empty_portfolio_returns_empty_allocation(self) -> None:
        self.assertEqual(AutonomousResourceBudgeter().allocate([]), [])

    def test_validates_normalized_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "priority_score"):
            AutonomousResourceBudgeter().allocate([demand(priority_score=1.2)])

    def test_writes_versioned_artifact(self) -> None:
        budgeter = AutonomousResourceBudgeter()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resource_allocations.json"
            budgeter.write(budgeter.allocate([demand()]), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["allocation_count"], 1)


if __name__ == "__main__":
    unittest.main()
