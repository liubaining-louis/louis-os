from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from atlas.commercial_benchmark_runner import CommercialBenchmarkRunner
from atlas.economic_outcome_ledger import EconomicOutcome
from atlas.live_mission_runner import LiveSignal, MissionInput, ProspectCandidate
from atlas.real_market_experiment import MarketObservation, Prospect


class SignalAdapter:
    read_only = True

    def __init__(self, items):
        self.items = items

    def collect(self, mission, limit):
        return self.items


class ProspectAdapter:
    read_only = True

    def discover(self, mission, evidence, limit):
        return [ProspectCandidate("p1", "Industrial Buyer", 0.9, ("w1", "w2"))]


def mission():
    return MissionInput(
        mission_id="m1",
        objective="Validate a real industrial sourcing offer",
        offer="qualified sourcing and supplier validation",
        target_segment="European industrial SMEs",
        consent_scope="commercial_research",
        maximum_web_signals=5,
        maximum_gmail_signals=5,
        maximum_prospects=5,
    )


def web(index):
    return LiveSignal(f"w{index}", "web", f"verified market evidence {index}", f"https://example.com/{index}")


def prospect():
    return Prospect("p1", "Industrial Buyer", "email", 0.9, ("w1", "w2"))


class CommercialBenchmarkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = CommercialBenchmarkRunner()
        self.now = datetime(2026, 7, 18, 20, 0, tzinfo=timezone.utc)

    def test_connects_live_market_economic_and_scheduling_layers(self):
        result = self.runner.run(
            benchmark_id="bench-1",
            mission=mission(),
            opportunity_id="opp-1",
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([LiveSignal("g1", "gmail", "Please send a quotation", "gmail://thread/1")]),
            prospect_adapter=ProspectAdapter(),
            prospects=[prospect()],
            observations=[MarketObservation("p1", "commercial_intent", "Please quote", 5000)],
            outcomes=[EconomicOutcome("o1", "opp-1", "p1", "quote", 5000, 3000, 100, 0.5)],
            total_budget=100,
            now=self.now,
        )
        self.assertEqual(result.live_mission.qualified_prospects, 1)
        self.assertEqual(result.market_experiment.commercial_intents, 1)
        self.assertEqual(result.economic_summary.quotes, 1)
        self.assertEqual(result.demonstrated_chain[-1], "next_mission_selection")
        self.assertIn("no booked revenue demonstrated", result.blocking_reasons)

    def test_booked_order_removes_revenue_blocker(self):
        result = self.runner.run(
            benchmark_id="bench-2",
            mission=mission(),
            opportunity_id="opp-1",
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([LiveSignal("g1", "gmail", "Order confirmed", "gmail://thread/1")]),
            prospect_adapter=ProspectAdapter(),
            prospects=[prospect()],
            observations=[MarketObservation("p1", "commercial_intent", "Order confirmed", 5000)],
            outcomes=[EconomicOutcome("o1", "opp-1", "p1", "order", 5000, 3000, 100, 1.0)],
            total_budget=100,
            now=self.now,
        )
        self.assertNotIn("no booked revenue demonstrated", result.blocking_reasons)
        self.assertEqual(result.economic_summary.booked_gross_profit, 1900)

    def test_rejects_inconsistent_live_prospect_identity(self):
        with self.assertRaises(ValueError):
            self.runner.run(
                benchmark_id="bench-3",
                mission=mission(),
                opportunity_id="opp-1",
                web_adapter=SignalAdapter([web(1), web(2), web(3)]),
                gmail_adapter=SignalAdapter([]),
                prospect_adapter=ProspectAdapter(),
                prospects=[Prospect("other", "Other", "email", 0.9, ("w1",))],
                observations=[],
                outcomes=[],
                total_budget=100,
                now=self.now,
            )

    def test_writes_single_auditable_vertical_artifact(self):
        result = self.runner.run(
            benchmark_id="bench-4",
            mission=mission(),
            opportunity_id="opp-1",
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([]),
            prospect_adapter=ProspectAdapter(),
            prospects=[prospect()],
            observations=[MarketObservation("p1", "no_response")],
            outcomes=[EconomicOutcome("o1", "opp-1", "p1", "lead")],
            total_budget=100,
            now=self.now,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            self.runner.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["commercial_benchmark"]["benchmark_id"], "bench-4")
        self.assertIn("economic_summary", payload["commercial_benchmark"])


if __name__ == "__main__":
    unittest.main()
