import json
import tempfile
import unittest
from pathlib import Path

from atlas.autonomous_venture_cycle import (
    AutonomousVentureCycle,
    BaselineSnapshot,
    ExperimentObservation,
)
from atlas.venture_runtime import Opportunity


def opportunity(
    opportunity_id: str,
    *,
    expected_value: float = 0.9,
    autonomy: float = 0.9,
    human_dependency: float = 0.05,
) -> Opportunity:
    return Opportunity(
        opportunity_id=opportunity_id,
        title=f"Opportunity {opportunity_id}",
        problem="A verified recurring industrial sourcing problem",
        target_customer="European industrial SME",
        proposed_offer="Evidence-backed automated supplier intelligence brief",
        evidence_references=[f"evidence://{opportunity_id}"],
        expected_value=expected_value,
        autonomy=autonomy,
        learning_value=0.8,
        speed=0.8,
        human_dependency=human_dependency,
        cost=0.1,
        risk=0.1,
    )


class AutonomousVentureCycleTests(unittest.TestCase):
    def test_internal_cycle_promotes_only_after_measurement_and_baseline_comparison(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousVentureCycle().run(
                venture_id="venture-1",
                opportunities=[opportunity("winner"), opportunity("runner", expected_value=0.5)],
                baseline=BaselineSnapshot(
                    decision_score=0.5,
                    autonomy=0.8,
                    unsupported_claims=0,
                ),
                output_dir=tmpdir,
                success_threshold=0.7,
                observation=ExperimentObservation(
                    metric_name="validation_score",
                    metric_value=0.8,
                    evidence_references=["evidence://measurement-1"],
                ),
            )

            self.assertTrue(result.promoted)
            self.assertEqual(result.status, "learned")
            self.assertEqual(result.baseline_reference, "github://liubaining-louis/louis-os/issues/47")
            self.assertEqual(set(result.artifact_paths), {"decision", "experiment", "memory", "result"})
            for path in result.artifact_paths.values():
                self.assertTrue(Path(path).exists())

            payload = json.loads(Path(result.artifact_paths["result"]).read_text(encoding="utf-8"))
            self.assertTrue(payload["promoted"])
            self.assertEqual(payload["metric_value"], 0.8)

    def test_external_action_is_blocked_without_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousVentureCycle().run(
                venture_id="venture-2",
                opportunities=[opportunity("winner")],
                baseline=BaselineSnapshot(decision_score=0.4, autonomy=0.7),
                output_dir=tmpdir,
                success_threshold=0.5,
                observation=ExperimentObservation(
                    metric_name="reply_rate",
                    metric_value=0.9,
                    evidence_references=["evidence://reply-rate"],
                ),
                external_action=True,
                approval_granted=False,
            )

            self.assertFalse(result.promoted)
            self.assertEqual(result.status, "approval_required")
            self.assertIn("requires human approval", result.reasons[0])

    def test_cycle_refuses_promotion_when_unsupported_claims_increase(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousVentureCycle().run(
                venture_id="venture-3",
                opportunities=[opportunity("winner")],
                baseline=BaselineSnapshot(
                    decision_score=0.4,
                    autonomy=0.7,
                    unsupported_claims=0,
                ),
                output_dir=tmpdir,
                success_threshold=0.5,
                observation=ExperimentObservation(
                    metric_name="validation_score",
                    metric_value=0.9,
                    evidence_references=["evidence://measurement-3"],
                    unsupported_claims=1,
                ),
            )

            self.assertFalse(result.promoted)
            self.assertTrue(any("unsupported claims increased" in reason for reason in result.reasons))

    def test_cycle_requires_a_measurable_observation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousVentureCycle().run(
                venture_id="venture-4",
                opportunities=[opportunity("winner")],
                baseline=BaselineSnapshot(decision_score=0.4, autonomy=0.7),
                output_dir=tmpdir,
                success_threshold=0.5,
            )

            self.assertFalse(result.promoted)
            self.assertEqual(result.status, "measurement_required")
            self.assertIn("no measurable observation", result.reasons[0])


if __name__ == "__main__":
    unittest.main()
