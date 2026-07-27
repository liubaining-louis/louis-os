from __future__ import annotations

import unittest

from atlas.cash_first_market import (
    assess_cash_priority,
    build_cash_first_portfolio,
    human_action_payload,
    prioritize_capability_backlog,
)


class CashFirstMarketTests(unittest.TestCase):
    def opportunity(self, **overrides):
        values = {
            "opportunity_id": "market-small",
            "source_id": "official",
            "source_category": "code_bounty",
            "source_url": "https://example.org/small",
            "title": "Small paid fix",
            "description": "Fix one deterministic issue.",
            "reward_amount": 300.0,
            "currency": "EUR",
            "reward_verified": True,
            "payment_evidence": ["https://example.org/small#payment"],
            "required_capabilities": ["validated_patch"],
            "observed_at": "2026-07-26T20:00:00+00:00",
            "deadline": "2026-08-01",
            "account_required": False,
            "terms_required": False,
            "legal_entity_required": False,
            "identity_or_kyc_required": False,
            "security_scope_authorized": True,
            "physical_presence_required": False,
            "accessibility": 0.95,
            "human_dependency": 0.05,
            "risk": 0.10,
            "cost": 0.05,
            "competition": 0.20,
            "time_to_cash_days": 7,
            "evidence": ["https://example.org/rules"],
            "metadata": {"estimated_effort_hours": 4, "payment_methods": ["bank transfer", "PayPal"]},
            "decision": {
                "status": "executable_now",
                "score": 70.0,
                "missing_capabilities": [],
                "blockers": [],
                "next_action": "execute",
                "human_action_minimal": "none",
                "evidence": ["https://example.org/rules"],
            },
        }
        values.update(overrides)
        return values

    def test_small_fast_mission_outranks_large_slow_contest(self) -> None:
        small = self.opportunity()
        large = self.opportunity(
            opportunity_id="market-large",
            source_category="challenge_prize",
            source_url="https://example.org/large",
            title="Million euro contest",
            reward_amount=1_000_000,
            competition=0.90,
            cost=0.40,
            time_to_cash_days=180,
            metadata={"estimated_effort_hours": 240},
            decision={
                "status": "capability_build",
                "score": 90.0,
                "missing_capabilities": ["large_prototype"],
                "blockers": ["capability_missing:large_prototype"],
                "next_action": "build",
                "human_action_minimal": "none",
                "evidence": [],
            },
        )
        portfolio = build_cash_first_portfolio(
            {"generated_at": "2026-07-26T20:00:00+00:00", "opportunities": [large, small]}
        )
        self.assertEqual(portfolio["top_cash_first"]["opportunity_id"], "market-small")
        self.assertEqual(portfolio["counts"]["cash_first"], 1)
        self.assertEqual(portfolio["counts"]["strategic"], 1)
        self.assertGreater(
            portfolio["cash_first"][0]["cash_priority_score"],
            portfolio["strategic"][0]["cash_priority_score"],
        )

    def test_all_lawful_payment_methods_are_recorded_not_used_as_rejection(self) -> None:
        assessment = assess_cash_priority(self.opportunity())
        self.assertEqual(assessment.lane, "cash_first")
        self.assertEqual(assessment.payment_methods, ("bank transfer", "PayPal"))

    def test_ready_human_gate_creates_precise_notification(self) -> None:
        gated = self.opportunity(
            decision={
                "status": "prepare_then_gate",
                "score": 72.0,
                "missing_capabilities": [],
                "blockers": ["account_required", "identity_or_kyc_required"],
                "next_action": "request gate",
                "human_action_minimal": "account_required, identity_or_kyc_required",
                "evidence": [],
            },
            metadata={
                "estimated_effort_hours": 4,
                "payment_methods": ["Wise"],
                "payout_setup_required": True,
            },
        )
        portfolio = build_cash_first_portfolio(
            {"generated_at": "2026-07-26T20:00:00+00:00", "opportunities": [gated]}
        )
        alert = human_action_payload(portfolio)
        self.assertEqual(alert["status"], "action_required")
        self.assertEqual(alert["count"], 1)
        actions = alert["items"][0]["human_actions"]
        self.assertTrue(any("account" in item.lower() for item in actions))
        self.assertTrue(any("KYC" in item for item in actions))
        self.assertTrue(any("payout" in item.lower() for item in actions))

    def test_marketplace_gate_waits_until_proposal_dossier_is_prepared(self) -> None:
        decision = {
            "status": "prepare_then_gate",
            "score": 72.0,
            "missing_capabilities": [],
            "blockers": ["account_required", "terms_acceptance_required"],
            "next_action": "request gate",
            "human_action_minimal": "account_required, terms_acceptance_required",
            "evidence": [],
        }
        base_metadata = {
            "estimated_effort_hours": 8,
            "payment_methods": ["Freelancer milestone payment"],
            "submission_dossier_required": True,
            "submission_dossier_prepared": False,
        }
        unprepared = self.opportunity(
            source_id="freelancer_public_simple_jobs",
            source_category="freelance_marketplace",
            decision=decision,
            metadata=base_metadata,
        )
        portfolio = build_cash_first_portfolio(
            {"generated_at": "2026-07-26T20:00:00+00:00", "opportunities": [unprepared]}
        )
        self.assertEqual(portfolio["counts"]["human_action_ready"], 0)

        exact_instruction = "Authorize the truthful platform account and review the terms for this prepared proposal."
        prepared = self.opportunity(
            source_id="freelancer_public_simple_jobs",
            source_category="freelance_marketplace",
            decision=decision,
            metadata={
                **base_metadata,
                "submission_dossier_prepared": True,
                "proposal_path": "results/simple_mission_dossiers/market-small/proposal.md",
                "proposal_manifest_path": "results/simple_mission_dossiers/market-small/manifest.json",
                "human_action_instructions": [exact_instruction],
            },
        )
        portfolio = build_cash_first_portfolio(
            {"generated_at": "2026-07-26T20:00:00+00:00", "opportunities": [prepared]}
        )
        self.assertEqual(portfolio["counts"]["human_action_ready"], 1)
        item = portfolio["human_action_ready"][0]
        self.assertEqual(item["human_actions"], (exact_instruction,))
        self.assertEqual(len(item["prepared_artifacts"]), 2)
        self.assertIn("KYC", item["risk_summary"])

    def test_missing_capability_does_not_notify_owner_prematurely(self) -> None:
        blocked = self.opportunity(
            decision={
                "status": "capability_build",
                "score": 60.0,
                "missing_capabilities": ["new_capability"],
                "blockers": ["capability_missing:new_capability", "account_required"],
                "next_action": "build",
                "human_action_minimal": "none",
                "evidence": [],
            }
        )
        portfolio = build_cash_first_portfolio(
            {"generated_at": "2026-07-26T20:00:00+00:00", "opportunities": [blocked]}
        )
        self.assertEqual(portfolio["counts"]["human_action_ready"], 0)

    def test_strategic_capability_gap_is_deferred_behind_cash_first(self) -> None:
        market = {
            "generated_at": "2026-07-26T20:00:00+00:00",
            "opportunities": [
                self.opportunity(),
                self.opportunity(
                    opportunity_id="market-large",
                    source_category="challenge_prize",
                    source_url="https://example.org/large",
                    time_to_cash_days=120,
                    cost=0.4,
                    competition=0.8,
                    metadata={"estimated_effort_hours": 120},
                ),
            ],
        }
        portfolio = build_cash_first_portfolio(market)
        backlog = {
            "items": [
                {
                    "capability_id": "strategic_capability",
                    "priority_score": 90,
                    "originating_opportunity_ids": ["market-large"],
                    "issue": {
                        "title": "Capability gap: strategic_capability",
                        "body": "<!-- marker -->",
                        "marker": "<!-- marker -->",
                    },
                },
                {
                    "capability_id": "cash_capability",
                    "priority_score": 50,
                    "originating_opportunity_ids": ["market-small"],
                    "issue": {
                        "title": "Capability gap: cash_capability",
                        "body": "<!-- cash -->",
                        "marker": "<!-- cash -->",
                    },
                },
            ]
        }
        prioritized = prioritize_capability_backlog(backlog, portfolio)
        self.assertEqual(prioritized["items"][0]["capability_id"], "cash_capability")
        self.assertFalse(prioritized["items"][0]["deferred_by_cash_first"])
        self.assertTrue(prioritized["items"][1]["deferred_by_cash_first"])


if __name__ == "__main__":
    unittest.main()
