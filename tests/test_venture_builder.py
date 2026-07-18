from __future__ import annotations

import unittest

from atlas.venture_builder import (
    ComparativeScore,
    VentureExperiment,
    VentureState,
    VentureTransition,
    count_unsupported_numeric_claims,
    promote_candidate,
)


class VentureBuilderTests(unittest.TestCase):
    def test_valid_transition_requires_measurable_milestone(self) -> None:
        transition = VentureTransition(
            from_state=VentureState.OBSERVING,
            to_state=VentureState.HYPOTHESIZING,
            reason="Three evidenced buyer problems were found.",
            evidence_references=["web:source-1"],
            next_milestone="Produce three evidence-backed venture hypotheses.",
        )
        transition.validate()

    def test_invalid_transition_is_rejected(self) -> None:
        transition = VentureTransition(
            from_state=VentureState.OBSERVING,
            to_state=VentureState.SCALING,
            reason="Skip directly to scale.",
            evidence_references=[],
            next_milestone="Revenue.",
        )
        with self.assertRaises(ValueError):
            transition.validate()

    def test_experiment_requires_stop_rule_and_idempotency(self) -> None:
        experiment = VentureExperiment(
            experiment_id="exp-001",
            hypothesis="A compliance-monitoring brief solves a repeated buyer problem.",
            action="Generate a sample report from public evidence.",
            success_metric="Qualified buyer confirmations",
            success_threshold="At least 2 confirmations from 10 reviewed prospects",
            deadline="2026-08-01",
            stop_condition="Stop after 10 prospects or budget exhaustion.",
            budget_limit=20.0,
            idempotency_key="exp-001-v1",
            requires_approval=False,
            evidence_references=["web:source-1"],
        )
        experiment.validate()

    def test_unsupported_claim_detector_flags_baseline_style_numbers(self) -> None:
        text = "The market size is $100 million with growth potential of 20%. Potential is $15,000/year."
        self.assertGreaterEqual(count_unsupported_numeric_claims(text), 3)

    def test_no_promotion_when_candidate_has_no_artifact(self) -> None:
        baseline = ComparativeScore(2, 2, 2, 2, 1, 1, 1, 1, 1)
        candidate = ComparativeScore(3, 3, 3, 3, 3, 0, 3, 3, 3)
        promoted, reasons = promote_candidate(
            baseline,
            candidate,
            baseline_unsupported=4,
            candidate_unsupported=0,
        )
        self.assertFalse(promoted)
        self.assertIn("candidate produced no executable artifact", reasons)


if __name__ == "__main__":
    unittest.main()
