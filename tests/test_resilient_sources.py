from __future__ import annotations

import unittest

from atlas.opportunity_discovery import OpportunitySignal
from atlas.resilient_sources import ResilientCompositeOpportunitySource


def signal(source_id: str) -> OpportunitySignal:
    return OpportunitySignal(
        source_id=source_id,
        source_url="https://example.com/opportunity",
        title="Test opportunity",
        problem="A real problem",
        target_customer="B2B buyer",
        proposed_offer="Automated qualification",
        expected_value=0.8,
        autonomy=0.9,
        learning_value=0.7,
        speed=0.8,
        human_dependency=0.1,
        cost=0.2,
        risk=0.2,
        observed_at="2026-07-18T00:00:00Z",
    )


class GoodSource:
    source_name = "good"

    def collect(self):
        return [signal("good-1")]


class BrokenSource:
    source_name = "broken"

    def collect(self):
        raise TimeoutError("upstream timeout")


class ResilientCompositeOpportunitySourceTests(unittest.TestCase):
    def test_preserves_successful_signals_when_one_source_fails(self) -> None:
        source = ResilientCompositeOpportunitySource("resilient", [BrokenSource(), GoodSource()])

        signals = list(source.collect())

        self.assertEqual([item.source_id for item in signals], ["good-1"])
        self.assertEqual(len(source.statuses), 2)
        self.assertFalse(source.statuses[0].success)
        self.assertEqual(source.statuses[0].error_type, "TimeoutError")
        self.assertTrue(source.statuses[1].success)
        self.assertEqual(source.statuses[1].signal_count, 1)

    def test_fails_closed_when_every_source_fails(self) -> None:
        source = ResilientCompositeOpportunitySource("resilient", [BrokenSource(), BrokenSource()])

        with self.assertRaisesRegex(RuntimeError, "all opportunity sources failed"):
            list(source.collect())

    def test_rejects_non_source_objects(self) -> None:
        source = ResilientCompositeOpportunitySource("resilient", [object()])

        with self.assertRaisesRegex(TypeError, "implement collect"):
            list(source.collect())


if __name__ == "__main__":
    unittest.main()
