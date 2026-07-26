from __future__ import annotations

import unittest

from atlas.universal_market import (
    CapabilityDefinition,
    CapabilityRegistry,
    InternetOpportunity,
    SourceState,
    UniversalMarketEngine,
)


class UniversalMarketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            [
                CapabilityDefinition(
                    capability_id="validated_patch",
                    status="validated",
                    evidence=("tests/test_fixture.py",),
                    handler="fixture",
                    test_command="python -m unittest",
                ),
                CapabilityDefinition(
                    capability_id="experimental_proposal",
                    status="experimental",
                ),
                CapabilityDefinition(
                    capability_id="human_study",
                    status="forbidden",
                ),
            ]
        )
        self.engine = UniversalMarketEngine(self.registry)

    def opportunity(self, **overrides):
        values = {
            "source_id": "official-source",
            "source_category": "code_bounty",
            "source_url": "https://example.org/opportunities/1",
            "title": "Paid deterministic patch",
            "description": "Produce one tested patch.",
            "reward_amount": 500.0,
            "currency": "EUR",
            "reward_verified": True,
            "payment_evidence": ("https://example.org/opportunities/1#reward",),
            "required_capabilities": ("validated_patch",),
            "observed_at": "2026-07-26T20:00:00+00:00",
            "accessibility": 0.95,
            "human_dependency": 0.05,
            "risk": 0.1,
            "cost": 0.05,
            "competition": 0.2,
            "time_to_cash_days": 14,
            "evidence": ("https://example.org/rules",),
        }
        values.update(overrides)
        return InternetOpportunity(**values)

    def test_verified_supported_opportunity_is_executable_now(self) -> None:
        result = self.engine.evaluate([self.opportunity()])
        self.assertEqual(result.decisions[0].status, "executable_now")
        self.assertEqual(result.decisions[0].human_action_minimal, "none")

    def test_account_and_terms_gate_only_the_external_boundary(self) -> None:
        result = self.engine.evaluate(
            [self.opportunity(account_required=True, terms_required=True, identity_or_kyc_required=True)]
        )
        decision = result.decisions[0]
        self.assertEqual(decision.status, "prepare_then_gate")
        self.assertIn("account_required", decision.blockers)
        self.assertIn("terms_acceptance_required", decision.blockers)
        self.assertIn("identity_or_kyc_required", decision.blockers)

    def test_missing_capability_creates_market_backed_gap(self) -> None:
        result = self.engine.evaluate(
            [
                self.opportunity(
                    source_url="https://example.org/opportunities/2",
                    required_capabilities=("experimental_proposal", "new_solver"),
                    reward_amount=2000,
                )
            ]
        )
        self.assertEqual(result.decisions[0].status, "capability_build")
        ids = {gap.capability_id for gap in result.capability_gaps}
        self.assertEqual(ids, {"experimental_proposal", "new_solver"})
        for gap in result.capability_gaps:
            self.assertIn("acceptance_tests", gap.specification)
            self.assertTrue(gap.marker.startswith("<!-- louis-capability-gap:"))

    def test_unverified_reward_is_rejected_even_when_capability_exists(self) -> None:
        result = self.engine.evaluate(
            [
                self.opportunity(
                    reward_verified=False,
                    reward_amount=500,
                    payment_evidence=(),
                )
            ]
        )
        self.assertEqual(result.decisions[0].status, "rejected")
        self.assertIn("payment_unverified", result.decisions[0].blockers)

    def test_unauthorized_security_testing_is_rejected(self) -> None:
        result = self.engine.evaluate(
            [
                self.opportunity(
                    source_category="security_bounty",
                    security_scope_authorized=False,
                )
            ]
        )
        self.assertEqual(result.decisions[0].status, "rejected")
        self.assertIn("unauthorized_security_testing", result.decisions[0].blockers)

    def test_canonical_url_deduplication_keeps_stronger_record(self) -> None:
        weak = self.opportunity(reward_amount=100, source_url="https://example.org/opportunities/1?utm=x")
        strong = self.opportunity(reward_amount=900, source_url="https://example.org/opportunities/1#details")
        result = self.engine.evaluate([weak, strong])
        self.assertEqual(len(result.opportunities), 1)
        self.assertEqual(result.opportunities[0].reward_amount, 900)

    def test_failed_source_state_does_not_stop_other_opportunities(self) -> None:
        result = self.engine.evaluate(
            [self.opportunity()],
            [
                SourceState(
                    source_id="failed-source",
                    category="freelance",
                    status="failed",
                    reason="timeout",
                    evidence=("https://failed.example",),
                )
            ],
        )
        self.assertEqual(result.decisions[0].status, "executable_now")
        self.assertEqual(result.source_states[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
