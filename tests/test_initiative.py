import unittest

from atlas.initiative import (
    ActionBudget,
    Opportunity,
    opportunities_from_goals,
    select_opportunity,
)
from atlas.strategic_goals import StrategicGoal


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

    def test_active_goals_feed_initiative_selection(self):
        goals = [
            StrategicGoal("reliability", "Reliability", "atlas", "success_rate", 1.0, 0.95, "2026-Q4", priority=100),
            StrategicGoal("semantic", "Semantic memory", "atlas", "recall", 1.0, 0.20, "2026-Q3", priority=80),
        ]
        selected = select_opportunity(opportunities_from_goals(goals), ActionBudget())
        self.assertIsNotNone(selected)
        self.assertEqual(selected.key, "semantic")

    def test_inactive_and_completed_goals_do_not_create_opportunities(self):
        goals = [
            StrategicGoal("paused", "Paused", "atlas", "score", 1.0, 0.0, "2026-Q4", status="paused"),
            StrategicGoal("done", "Done", "atlas", "score", 1.0, 1.0, "2026-Q4", status="completed"),
            StrategicGoal("already-at-target", "At target", "atlas", "score", 1.0, 1.0, "2026-Q4"),
        ]
        self.assertEqual(opportunities_from_goals(goals), [])

    def test_goal_conversion_is_order_independent(self):
        goals = [
            StrategicGoal("b", "B", "atlas", "b", 1.0, 0.2, "2026-Q4", priority=60),
            StrategicGoal("a", "A", "atlas", "a", 1.0, 0.4, "2026-Q4", priority=70),
        ]
        self.assertEqual(opportunities_from_goals(goals), opportunities_from_goals(reversed(goals)))

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            Opportunity("x", 1, 1, 1.1, 1).score()
        with self.assertRaises(ValueError):
            ActionBudget(max_actions=-1).allows(Opportunity("x", 1, 1, 1.0, 1))
        with self.assertRaises(ValueError):
            opportunities_from_goals([], effort=-1)


if __name__ == "__main__":
    unittest.main()
