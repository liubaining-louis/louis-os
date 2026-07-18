import tempfile
import unittest

from atlas.autonomous_venture_cycle import BaselineSnapshot, ExperimentObservation
from atlas.opportunity_discovery import OpportunitySignal, StaticOpportunitySource
from atlas.opportunity_to_venture import OpportunityToVenturePipeline


class OpportunityToVenturePipelineTests(unittest.TestCase):
    def test_pipeline_discovers_then_runs_bounded_cycle(self):
        source = StaticOpportunitySource(
            "verified-feed",
            [
                OpportunitySignal(
                    source_id="signal-1",
                    source_url="https://example.com/signals/1",
                    title="Automated supplier intelligence",
                    problem="SMEs lack verified supplier intelligence",
                    target_customer="European industrial SME",
                    proposed_offer="Evidence-backed automated supplier intelligence brief",
                    expected_value=0.9,
                    autonomy=0.9,
                    learning_value=0.8,
                    speed=0.8,
                    human_dependency=0.1,
                    cost=0.1,
                    risk=0.1,
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = OpportunityToVenturePipeline().run(
                venture_id="venture-discovered-1",
                sources=[source],
                baseline=BaselineSnapshot(decision_score=0.4, autonomy=0.8),
                output_dir=tmpdir,
                success_threshold=0.7,
                observation=ExperimentObservation(
                    metric_name="validation_score",
                    metric_value=0.8,
                    evidence_references=["https://example.com/measurements/1"],
                ),
            )

            self.assertEqual(result.discovery.accepted_count, 1)
            self.assertIsNotNone(result.cycle)
            self.assertTrue(result.cycle.promoted)
            self.assertEqual(result.status, "learned")

    def test_pipeline_stops_when_every_signal_is_ineligible(self):
        source = StaticOpportunitySource(
            "manual-feed",
            [
                OpportunitySignal(
                    source_id="manual-1",
                    source_url="https://example.com/signals/manual",
                    title="Human sales consultancy",
                    problem="Requires daily negotiation",
                    target_customer="SME",
                    proposed_offer="Manual negotiation service",
                    expected_value=0.8,
                    autonomy=0.2,
                    learning_value=0.5,
                    speed=0.4,
                    human_dependency=0.9,
                    cost=0.3,
                    risk=0.2,
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = OpportunityToVenturePipeline().run(
                venture_id="venture-discovered-2",
                sources=[source],
                baseline=BaselineSnapshot(decision_score=0.4, autonomy=0.8),
                output_dir=tmpdir,
                success_threshold=0.7,
            )

            self.assertEqual(result.status, "no_eligible_opportunity")
            self.assertIsNone(result.cycle)


if __name__ == "__main__":
    unittest.main()
