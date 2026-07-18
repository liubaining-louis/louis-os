from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atlas.experiment_outcomes import ExperimentOutcome, ExperimentOutcomeEvaluator
from atlas.experiment_planner import ExperimentPlan


def plan() -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="exp-123",
        opportunity_id="opp-123",
        hypothesis="Qualified targets will show intent.",
        target_customer="B2B buyer",
        proposed_offer="Automated qualification",
        method=("dry run",),
        primary_metric="qualified_positive_intent_rate",
        success_threshold=0.30,
        maximum_cost_score=0.35,
        maximum_human_dependency=0.30,
        evidence_references=("https://example.com/evidence",),
    )


def outcome(*, positives: int, cost: float = 0.2, dependency: float = 0.2) -> ExperimentOutcome:
    return ExperimentOutcome(
        experiment_id="exp-123",
        sample_size=10,
        qualified_positive_count=positives,
        observed_cost_score=cost,
        observed_human_dependency=dependency,
        evidence_references=("artifact://experiment/result.json",),
    )


class ExperimentOutcomeEvaluatorTests(unittest.TestCase):
    def test_continues_when_threshold_is_met(self) -> None:
        evaluation = ExperimentOutcomeEvaluator().evaluate(plan(), outcome(positives=3))
        self.assertEqual(evaluation.decision, "continue")
        self.assertEqual(evaluation.observed_rate, 0.3)

    def test_revises_when_result_is_close_to_threshold(self) -> None:
        evaluation = ExperimentOutcomeEvaluator(revision_margin=0.10).evaluate(plan(), outcome(positives=2))
        self.assertEqual(evaluation.decision, "revise")

    def test_stops_when_threshold_is_missed(self) -> None:
        evaluation = ExperimentOutcomeEvaluator().evaluate(plan(), outcome(positives=1))
        self.assertEqual(evaluation.decision, "stop")

    def test_stops_when_cost_gate_is_exceeded_even_if_metric_succeeds(self) -> None:
        evaluation = ExperimentOutcomeEvaluator().evaluate(plan(), outcome(positives=8, cost=0.5))
        self.assertEqual(evaluation.decision, "stop")
        self.assertIn("cost", evaluation.reasons[0])

    def test_rejects_mismatched_experiment(self) -> None:
        bad = ExperimentOutcome(
            experiment_id="exp-other",
            sample_size=10,
            qualified_positive_count=5,
            observed_cost_score=0.1,
            observed_human_dependency=0.1,
            evidence_references=("artifact://result",),
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            ExperimentOutcomeEvaluator().evaluate(plan(), bad)

    def test_writes_versioned_artifact(self) -> None:
        evaluation = ExperimentOutcomeEvaluator().evaluate(plan(), outcome(positives=3))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "evaluation.json"
            written = ExperimentOutcomeEvaluator().write([evaluation], path)
            self.assertEqual(written, str(path))
            self.assertIn('"schema_version": "1.0"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
