import unittest

from atlas.strategic_decision import (
    CandidateAction,
    DecisionOutcome,
    RiskAssessment,
    select_strategic_action,
)


def candidate(
    action_id: str,
    *,
    evidence: tuple[str, ...] = ("evidence:1",),
    value: float = 0.7,
    confidence: float = 0.8,
    effort: int = 2,
    token_cost: int = 1000,
    monetary_cost: float = 0.0,
    reversibility: float = 1.0,
    information_gain: float = 0.5,
    risk: int = 1,
    approval: bool = False,
) -> CandidateAction:
    return CandidateAction(
        action_id=action_id,
        goal_ids=("goal:reliability",),
        evidence_refs=evidence,
        expected_value=value,
        confidence=confidence,
        effort=effort,
        token_cost=token_cost,
        monetary_cost=monetary_cost,
        reversibility=reversibility,
        information_gain=information_gain,
        risk=RiskAssessment(technical=risk),
        requires_approval=approval,
    )


class StrategicDecisionTests(unittest.TestCase):
    def test_selects_highest_value_safe_candidate(self):
        result = select_strategic_action(
            [candidate("small", value=0.4), candidate("large", value=0.9)]
        )
        self.assertEqual(result.status, "proposed")
        self.assertEqual(result.recommended_action_id, "large")

    def test_order_and_decision_id_are_deterministic(self):
        actions = [candidate("b"), candidate("a")]
        first = select_strategic_action(actions)
        second = select_strategic_action(reversed(actions))
        self.assertEqual(first, second)
        self.assertEqual(first.to_json(), second.to_json())

    def test_missing_evidence_fails_closed(self):
        result = select_strategic_action([candidate("x", evidence=())])
        self.assertEqual(result.status, "no_action")
        self.assertIsNone(result.recommended_action_id)
        self.assertEqual(result.reason, "missing evidence")

    def test_high_risk_routes_to_approval(self):
        result = select_strategic_action([candidate("risky", risk=8)])
        self.assertEqual(result.status, "approval_required")
        self.assertEqual(result.recommended_action_id, "risky")

    def test_explicit_approval_routes_to_approval(self):
        result = select_strategic_action([candidate("external", approval=True)])
        self.assertEqual(result.status, "approval_required")

    def test_candidates_over_budget_are_not_selected(self):
        result = select_strategic_action([candidate("expensive", monetary_cost=50.0)])
        self.assertEqual(result.status, "no_action")
        self.assertEqual(result.reason, "all candidates exceed budget")

    def test_empty_candidates_return_no_action(self):
        result = select_strategic_action([])
        self.assertEqual(result.status, "no_action")

    def test_invalid_contract_values_are_rejected(self):
        with self.assertRaises(ValueError):
            candidate("x", confidence=1.1).score()
        with self.assertRaises(ValueError):
            select_strategic_action([], max_risk=-1)
        with self.assertRaises(ValueError):
            DecisionOutcome("d", "pending", observed_value=2.0).validate()


if __name__ == "__main__":
    unittest.main()
