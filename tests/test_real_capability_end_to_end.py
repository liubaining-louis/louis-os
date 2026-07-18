from __future__ import annotations

import unittest

from atlas.action_authorization import ActionAuthorizationGate, ProposedAction
from atlas.opportunity_portfolio import OpportunityPortfolioManager
from atlas.resource_budgeter import AutonomousResourceBudgeter, ResourceDemand
from atlas.venture_runtime import Opportunity


def opportunity(opportunity_id: str, **overrides) -> Opportunity:
    values = {
        "title": opportunity_id,
        "problem": "A measurable customer problem",
        "target_customer": "European industrial SMEs",
        "proposed_offer": "A bounded validation offer",
        "evidence_references": ["evidence://source/1", "evidence://source/2"],
        "expected_value": 0.60,
        "autonomy": 0.70,
        "learning_value": 0.60,
        "speed": 0.60,
        "human_dependency": 0.20,
        "cost": 0.20,
        "risk": 0.20,
    }
    values.update(overrides)
    return Opportunity(opportunity_id=opportunity_id, **values)


class RealCapabilityEndToEndTest(unittest.TestCase):
    """Stress the actual deterministic autonomy chain on competing venture options."""

    def test_selects_bounded_portfolio_allocates_resources_and_blocks_external_execution(self) -> None:
        candidates = [
            opportunity(
                "industrial-sourcing-agent",
                expected_value=0.88,
                autonomy=0.86,
                learning_value=0.78,
                speed=0.82,
                human_dependency=0.12,
                cost=0.10,
                risk=0.14,
                evidence_references=["evidence://client/1", "evidence://supplier/1", "evidence://market/1"],
            ),
            opportunity(
                "charcoal-import",
                expected_value=0.82,
                autonomy=0.40,
                learning_value=0.72,
                speed=0.28,
                human_dependency=0.55,
                cost=0.72,
                risk=0.62,
            ),
            opportunity(
                "automated-market-brief",
                expected_value=0.66,
                autonomy=0.94,
                learning_value=0.64,
                speed=0.92,
                human_dependency=0.05,
                cost=0.05,
                risk=0.08,
                evidence_references=["evidence://usage/1", "evidence://usage/2", "evidence://usage/3"],
            ),
            opportunity(
                "speculative-high-return",
                expected_value=0.98,
                autonomy=0.40,
                learning_value=0.30,
                speed=0.40,
                human_dependency=0.65,
                cost=0.85,
                risk=0.95,
            ),
            opportunity(
                "weak-evidence-idea",
                expected_value=0.75,
                autonomy=0.75,
                evidence_references=["evidence://single-claim"],
            ),
        ]

        portfolio = OpportunityPortfolioManager(maximum_active=2).allocate(candidates)
        by_id = {entry.opportunity_id: entry for entry in portfolio}

        self.assertEqual(by_id["industrial-sourcing-agent"].decision, "invest")
        self.assertEqual(by_id["automated-market-brief"].decision, "invest")
        self.assertNotEqual(by_id["speculative-high-return"].decision, "invest")
        self.assertEqual(sum(entry.decision == "invest" for entry in portfolio), 2)
        self.assertAlmostEqual(sum(entry.resource_share for entry in portfolio), 1.0, places=5)

        demands = [
            ResourceDemand(
                opportunity_id=entry.opportunity_id,
                priority_score=entry.score,
                requested_attention=0.70 if entry.decision == "invest" else 0.10,
                requested_compute=0.65 if entry.decision == "invest" else 0.10,
                requested_cost=0.20 if entry.decision == "invest" else 0.05,
                evidence_confidence=entry.confidence if entry.decision == "invest" else 0.10,
            )
            for entry in portfolio
        ]
        allocations = AutonomousResourceBudgeter(
            total_attention_budget=0.80,
            total_compute_budget=0.70,
            total_cost_budget=0.18,
        ).allocate(demands)
        allocation_by_id = {item.opportunity_id: item for item in allocations}

        self.assertIn(allocation_by_id["industrial-sourcing-agent"].decision, {"allocate", "throttle"})
        self.assertIn(allocation_by_id["automated-market-brief"].decision, {"allocate", "throttle"})
        self.assertEqual(allocation_by_id["weak-evidence-idea"].decision, "defer")
        self.assertLessEqual(sum(item.attention_budget for item in allocations), 0.80 + 1e-6)
        self.assertLessEqual(sum(item.compute_budget for item in allocations), 0.70 + 1e-6)
        self.assertLessEqual(sum(item.cost_budget for item in allocations), 0.18 + 1e-6)

        gate = ActionAuthorizationGate()
        internal = gate.classify(ProposedAction(
            action_id="prepare-analysis",
            action_type="write_local_artifact",
            scope="internal",
            estimated_cost_score=0.05,
            human_dependency=0.05,
            reversible=True,
            evidence_references=("evidence://portfolio/result",),
        ))
        external = gate.classify(ProposedAction(
            action_id="send-prospect-email",
            action_type="outreach",
            scope="external",
            estimated_cost_score=0.02,
            human_dependency=0.05,
            reversible=False,
            evidence_references=("evidence://portfolio/result",),
        ))

        self.assertEqual(internal.decision, "auto_execute")
        self.assertEqual(external.decision, "requires_approval")


if __name__ == "__main__":
    unittest.main()
