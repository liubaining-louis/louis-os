from __future__ import annotations

import unittest

from atlas.decision_intelligence import DecisionCase, DecisionIntelligence, LessonRegistry


class DecisionIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DecisionIntelligence(LessonRegistry())

    def case(self, **facts):
        base = {
            "listing_open": True,
            "buyer_seeking_worker": True,
            "reward_verified": True,
            "acceptance_criteria": ["deliver tested artifact"],
            "remote_eligible": True,
            "platform_compliant": True,
            "estimated_hours": 2,
            "reward_amount": 40,
            "minimum_hourly": 8,
            "external_action": True,
            "receipt_capture_planned": True,
            "source_kind": "public_freelance_listing",
            "title": "Small Python automation",
        }
        base.update(facts)
        return DecisionCase(
            case_id="case-1",
            domain="monetization",
            objective="earn first verified euro",
            facts=base,
            proposed_action="submit a bounded proposal",
            evidence=("https://example.org/job",),
        )

    def test_verified_reversible_case_can_proceed(self) -> None:
        result = self.engine.evaluate(self.case())
        self.assertEqual(result.decision, "proceed_reversibly")
        self.assertFalse(result.blockers)

    def test_missing_truth_evidence_requires_reverification(self) -> None:
        result = self.engine.evaluate(self.case(listing_open=None, buyer_seeking_worker=None))
        self.assertEqual(result.decision, "verify_then_reconsider")
        self.assertIn("fresh_open_status", result.critique.missing_evidence)
        self.assertIn("buyer_intent", result.critique.missing_evidence)

    def test_commercial_offer_and_proxy_bypass_are_rejected(self) -> None:
        case = DecisionCase(
            case_id="case-2",
            domain="monetization",
            objective="select opportunity",
            facts={
                "listing_open": True,
                "buyer_seeking_worker": True,
                "reward_verified": True,
                "acceptance_criteria": ["unknown"],
                "remote_eligible": True,
                "platform_compliant": False,
            },
            proposed_action="buy my proxy service and bypass anti-bot detection",
        )
        result = self.engine.evaluate(case)
        self.assertEqual(result.decision, "reject")
        self.assertIn("commercial_offer_not_job", result.blockers)
        self.assertIn("platform_policy_blocked", result.blockers)

    def test_low_hourly_value_is_rejected(self) -> None:
        result = self.engine.evaluate(self.case(estimated_hours=10, reward_amount=20))
        self.assertEqual(result.decision, "reject")
        self.assertIn("economically_unviable", result.blockers)

    def test_external_action_without_receipt_requires_mitigation(self) -> None:
        result = self.engine.evaluate(self.case(receipt_capture_planned=False))
        self.assertEqual(result.decision, "prepare_with_mitigation")
        self.assertIn("external_action_without_receipt", result.critique.failure_modes)

    def test_false_positive_becomes_reusable_blocking_lesson(self) -> None:
        case = self.case(title="Retail in-person sales promoter")
        first = self.engine.evaluate(case)
        lesson = self.engine.learn_from_outcome(
            case,
            first,
            outcome="false_positive",
            evidence=("results/reviewed_false_positive.json",),
        )
        self.assertIsNotNone(lesson)

        second = self.engine.evaluate(self.case(title="Another retail in-person sales promoter"))
        self.assertTrue(second.applied_lessons)
        self.assertEqual(second.decision, "reject")

    def test_learning_without_evidence_is_forbidden(self) -> None:
        case = self.case()
        result = self.engine.evaluate(case)
        with self.assertRaises(ValueError):
            self.engine.learn_from_outcome(case, result, outcome="success", evidence=())


if __name__ == "__main__":
    unittest.main()
