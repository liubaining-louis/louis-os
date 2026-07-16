import unittest

from atlas.initiative import ActionBudget, Opportunity, select_opportunity


class InitiativeTests(unittest.TestCase):
    def test_selects_highest_scoring_safe_opportunity(self):
        selected = select_opportunity(
            [
                Opportunity("semantic", impact=7, urgency=4, confidence=0.8, effort=5, risk=1),
                Opportunity("initiative", impact=9, urgency=8, confidence=0.9, effort=4, risk=1),
            ],
            ActionBudget(max_actions=1, max_risk=2),
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.key, "initiative")

    def test_approval_required_is_not_autonomously_selected(self):
        selected = select_opportunity(
            [Opportunity("iam", 10, 10, 1.0, 1, risk=1, requires_approval=True)],
            ActionBudget(),
        )
        self.assertIsNone(selected)

    def test_risk_and_action_budget_stop_execution(self):
        opportunity = Opportunity("risky", 10, 10, 1.0, 1, risk=3)
        self.assertIsNone(select_opportunity([opportunity], ActionBudget(max_risk=2)))
        safe = Opportunity("safe", 5, 5, 1.0, 1, risk=1)
        self.assertIsNone(select_opportunity([safe], ActionBudget(max_actions=1), actions_used=1))

    def test_tie_breaking_is_deterministic(self):
        opportunities = [
            Opportunity("b", 5, 5, 1.0, 2),
            Opportunity("a", 5, 5, 1.0, 2),
        ]
        first = select_opportunity(opportunities, ActionBudget())
        second = select_opportunity(reversed(opportunities), ActionBudget())
        self.assertEqual(first, second)

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            Opportunity("x", 1, 1, 1.1, 1).score()
        with self.assertRaises(ValueError):
            ActionBudget(max_actions=-1).allows(Opportunity("x", 1, 1, 1.0, 1))


if __name__ == "__main__":
    unittest.main()
