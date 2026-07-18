from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.opportunity_portfolio import OpportunityPortfolioManager
from atlas.venture_runtime import Opportunity


def opportunity(opportunity_id: str, **overrides) -> Opportunity:
    values = {
        "opportunity_id": opportunity_id,
        "title": f"Opportunity {opportunity_id}",
        "problem": "A measurable business problem",
        "target_customer": "industrial buyers",
        "proposed_offer": "a bounded sourcing service",
        "evidence_references": [f"https://example.com/{opportunity_id}"],
        "expected_value": 0.80,
        "autonomy": 0.90,
        "learning_value": 0.70,
        "speed": 0.80,
        "human_dependency": 0.10,
        "cost": 0.15,
        "risk": 0.20,
    }
    values.update(overrides)
    return Opportunity(**values)


class OpportunityPortfolioManagerTests(unittest.TestCase):
    def test_limits_active_portfolio_and_normalizes_resource_shares(self) -> None:
        manager = OpportunityPortfolioManager(maximum_active=2)
        entries = manager.allocate(
            [
                opportunity("opp-a", expected_value=0.95),
                opportunity("opp-b", expected_value=0.80),
                opportunity("opp-c", expected_value=0.60),
            ]
        )
        active = [item for item in entries if item.decision == "invest"]
        self.assertEqual(len(active), 2)
        self.assertAlmostEqual(sum(item.resource_share for item in active), 1.0, places=5)
        self.assertEqual(entries[0].opportunity_id, "opp-a")

    def test_more_evidence_improves_confidence_and_rank(self) -> None:
        manager = OpportunityPortfolioManager(maximum_active=1)
        entries = manager.allocate(
            [
                opportunity("opp-low", evidence_references=["https://example.com/1"]),
                opportunity(
                    "opp-high",
                    evidence_references=[
                        "https://example.com/1",
                        "https://example.com/2",
                        "https://example.com/3",
                    ],
                ),
            ]
        )
        self.assertEqual(entries[0].opportunity_id, "opp-high")
        self.assertGreater(entries[0].confidence, entries[1].confidence)

    def test_weak_opportunity_is_archived(self) -> None:
        manager = OpportunityPortfolioManager()
        entry = manager.allocate(
            [
                opportunity(
                    "opp-weak",
                    expected_value=0.05,
                    autonomy=0.05,
                    learning_value=0.05,
                    speed=0.05,
                    human_dependency=0.95,
                    cost=0.95,
                    risk=0.95,
                )
            ]
        )[0]
        self.assertEqual(entry.decision, "archive")
        self.assertEqual(entry.resource_share, 0.0)

    def test_ties_are_deterministic(self) -> None:
        manager = OpportunityPortfolioManager(maximum_active=1)
        entries = manager.allocate([opportunity("opp-b"), opportunity("opp-a")])
        self.assertEqual(entries[0].opportunity_id, "opp-a")

    def test_writes_versioned_portfolio_artifact(self) -> None:
        manager = OpportunityPortfolioManager(maximum_active=1)
        entries = manager.allocate([opportunity("opp-a"), opportunity("opp-b")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.json"
            manager.write(entries, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["portfolio_count"], 2)
        self.assertEqual(payload["active_count"], 1)


if __name__ == "__main__":
    unittest.main()
