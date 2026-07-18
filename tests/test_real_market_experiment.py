from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.real_market_experiment import MarketObservation, Prospect, RealMarketExperimentLoop


def prospect(prospect_id: str, fit_score: float = 0.8) -> Prospect:
    return Prospect(
        prospect_id=prospect_id,
        organization=f"Org {prospect_id}",
        contact_channel="email",
        fit_score=fit_score,
        evidence_ids=(f"e-{prospect_id}",),
    )


class RealMarketExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = RealMarketExperimentLoop(minimum_sample_size=5)

    def test_qualifies_only_evidence_backed_high_fit_prospects(self):
        result = self.loop.qualify([prospect("low", 0.4), prospect("high", 0.9)])
        self.assertEqual([item.prospect_id for item in result], ["high"])

    def test_outreach_is_never_auto_sent(self):
        item = self.loop.draft_outreach(
            prospect("p1"), offer="industrial sourcing", value_proposition="Reduce qualified sourcing effort."
        )
        self.assertEqual(item.authorization, "requires_approval")
        self.assertIn("human approval", item.rationale)

    def test_continues_when_sample_is_too_small(self):
        prospects = self.loop.qualify([prospect("p1"), prospect("p2")])
        drafts = [self.loop.draft_outreach(item, offer="offer", value_proposition="value") for item in prospects]
        observations = [MarketObservation("p1", "positive")]
        result = self.loop.evaluate("opp-1", prospects, drafts, observations)
        self.assertEqual(result.decision, "continue")

    def test_promotes_only_with_real_commercial_intent(self):
        prospects = self.loop.qualify([prospect(f"p{i}") for i in range(5)])
        drafts = [self.loop.draft_outreach(item, offer="offer", value_proposition="value") for item in prospects]
        observations = [
            MarketObservation("p0", "commercial_intent", estimated_value=5000),
            MarketObservation("p1", "positive"),
            MarketObservation("p2", "neutral"),
            MarketObservation("p3", "no_response"),
            MarketObservation("p4", "negative"),
        ]
        result = self.loop.evaluate("opp-1", prospects, drafts, observations)
        self.assertEqual(result.decision, "promote")
        self.assertEqual(result.estimated_pipeline_value, 5000)
        self.assertEqual(result.commercial_intents, 1)

    def test_stops_when_market_signal_is_too_weak(self):
        prospects = self.loop.qualify([prospect(f"p{i}") for i in range(5)])
        observations = [MarketObservation(item.prospect_id, "no_response") for item in prospects]
        result = self.loop.evaluate("opp-1", prospects, [], observations)
        self.assertEqual(result.decision, "stop")

    def test_revises_intermediate_result(self):
        prospects = self.loop.qualify([prospect(f"p{i}") for i in range(5)])
        observations = [
            MarketObservation("p0", "positive"),
            MarketObservation("p1", "neutral"),
            MarketObservation("p2", "no_response"),
            MarketObservation("p3", "negative"),
            MarketObservation("p4", "negative"),
        ]
        result = self.loop.evaluate("opp-1", prospects, [], observations)
        self.assertEqual(result.decision, "revise")

    def test_rejects_observation_for_unknown_prospect(self):
        with self.assertRaises(ValueError):
            self.loop.evaluate(
                "opp-1", [prospect("known")], [], [MarketObservation("unknown", "positive")]
            )

    def test_writes_auditable_market_artifact(self):
        prospects = self.loop.qualify([prospect(f"p{i}") for i in range(5)])
        result = self.loop.evaluate(
            "opp-1", prospects, [], [MarketObservation(item.prospect_id, "no_response") for item in prospects]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market_result.json"
            self.loop.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["market_experiment"]["decision"], "stop")


if __name__ == "__main__":
    unittest.main()
