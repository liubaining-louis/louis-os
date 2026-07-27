from __future__ import annotations

import unittest

from atlas.capability_market import (
    build_capability_plans,
    cluster_opportunities,
    enrich_capability_backlog,
    explicitly_prohibits_ai,
    reject_ai_prohibited_opportunities,
    simulate_cluster_revenue,
)


class CapabilityMarketTests(unittest.TestCase):
    def opportunity(self, **overrides):
        value = {
            "opportunity_id": "market-research-1",
            "source_id": "freelancer_public_simple_jobs",
            "source_category": "freelance_marketplace",
            "source_url": "https://example.test/research-1",
            "title": "Verified company research",
            "description": "Research public company websites and deliver a sourced spreadsheet.",
            "reward_amount": 80.0,
            "currency": "USD",
            "reward_verified": True,
            "payment_evidence": ["https://example.test/research-1#budget"],
            "required_capabilities": ["evidence_research_dossier"],
            "deadline": "5 days left",
            "accessibility": 0.90,
            "competition": 0.10,
            "risk": 0.10,
            "cost": 0.05,
            "human_dependency": 0.20,
            "time_to_cash_days": 21,
            "evidence": ["https://example.test/research-1"],
            "metadata": {"estimated_effort_hours": 8.0},
            "decision": {
                "status": "prepare_then_gate",
                "missing_capabilities": [],
                "blockers": ["account_required", "terms_acceptance_required"],
                "evidence": ["https://example.test/research-1"],
            },
        }
        value.update(overrides)
        return value

    def test_rejects_exact_ai_forbidden_memoir_before_capability_build(self) -> None:
        memoir = self.opportunity(
            opportunity_id="market-memoir",
            title="Descriptive Memoir Development & Polish",
            description=(
                "Develop and polish a memoir. Absolutely no AI-generated wording is acceptable; "
                "the client requires human-written text only."
            ),
            required_capabilities=["structured_document_delivery"],
            decision={
                "status": "capability_build",
                "missing_capabilities": ["structured_document_delivery"],
                "blockers": ["capability_missing:structured_document_delivery"],
                "evidence": [],
            },
        )
        self.assertTrue(explicitly_prohibits_ai(memoir))
        rows, rejected = reject_ai_prohibited_opportunities([memoir])
        self.assertEqual(rejected, 1)
        self.assertEqual(rows[0]["decision"]["status"], "rejected")
        self.assertEqual(rows[0]["decision"]["missing_capabilities"], [])
        self.assertIn("automation_prohibited_by_payer", rows[0]["decision"]["blockers"])
        self.assertEqual(rows[0]["metadata"]["policy_rejection"], "automation_prohibited_by_payer")

    def test_clusters_similar_research_missions_across_sources(self) -> None:
        first = self.opportunity()
        second = self.opportunity(
            opportunity_id="market-research-2",
            source_id="guru_public_simple_jobs",
            source_url="https://example.test/research-2",
            title="Public supplier contact research",
            description="Build a sourced contact list using official public websites.",
            reward_amount=100.0,
            currency="USD",
            competition=0.15,
        )
        clusters = cluster_opportunities(
            [first, second],
            {"evidence_research_dossier": "validated"},
        )
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.capability_id, "evidence_research_dossier")
        self.assertEqual(cluster.lane, "cash_first")
        self.assertEqual(cluster.opportunity_count, 2)
        self.assertEqual(cluster.source_count, 2)
        self.assertEqual(cluster.verified_value_by_currency["USD"], 180.0)
        self.assertGreater(cluster.reusable_deliverable_ratio, 0.55)

    def test_cash_first_cluster_outranks_huge_strategic_prize(self) -> None:
        small = self.opportunity(
            required_capabilities=["structured_document_delivery"],
            title="Proofread a short report",
            description="Proofread and format a 20-page report. AI-assisted editing is allowed.",
            reward_amount=120.0,
        )
        strategic = self.opportunity(
            opportunity_id="market-million-prize",
            source_id="usagov_challenges",
            source_category="challenge_prize",
            source_url="https://example.test/million-prize",
            title="Large strategic challenge",
            description="Build a large multi-year prototype.",
            reward_amount=15_000_000.0,
            required_capabilities=["technical_proposal"],
            accessibility=0.55,
            competition=0.80,
            risk=0.25,
            cost=0.25,
            time_to_cash_days=120,
            metadata={"estimated_effort_hours": 120.0},
            decision={
                "status": "capability_build",
                "missing_capabilities": ["technical_proposal"],
                "blockers": ["capability_missing:technical_proposal"],
                "evidence": [],
            },
        )
        clusters = cluster_opportunities(
            [strategic, small],
            {
                "structured_document_delivery": "experimental",
                "technical_proposal": "experimental",
            },
        )
        self.assertEqual(clusters[0].capability_id, "structured_document_delivery")
        self.assertEqual(clusters[0].lane, "cash_first")
        self.assertEqual(clusters[1].lane, "strategic")
        self.assertGreater(clusters[0].capability_market_score, clusters[1].capability_market_score)
        self.assertLessEqual(clusters[1].capped_score_value, 1_000.0)

    def test_revenue_simulation_never_counts_as_pipeline_or_revenue(self) -> None:
        opportunities = [self.opportunity()]
        cluster = cluster_opportunities(
            opportunities,
            {"evidence_research_dossier": "validated"},
        )[0]
        simulation = simulate_cluster_revenue(cluster, opportunities)
        self.assertEqual(simulation["type"], "simulation_only")
        self.assertFalse(simulation["counted_as_pipeline"])
        self.assertFalse(simulation["counted_as_revenue"])
        self.assertEqual(simulation["annualization_status"], "insufficient_history")
        self.assertIn("USD", simulation["scenarios_by_currency"])

    def test_build_plan_is_bounded_and_backlog_is_market_ranked(self) -> None:
        opportunity = self.opportunity(
            opportunity_id="market-doc-1",
            title="Proofread and format a short report",
            description="Proofread a report and return a tracked, formatted document.",
            reward_amount=150.0,
            required_capabilities=["structured_document_delivery"],
            decision={
                "status": "capability_build",
                "missing_capabilities": ["structured_document_delivery"],
                "blockers": ["capability_missing:structured_document_delivery"],
                "evidence": [],
            },
        )
        clusters = cluster_opportunities(
            [opportunity],
            {"structured_document_delivery": "experimental"},
        )
        plans = build_capability_plans(clusters)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.capability_id, "structured_document_delivery")
        self.assertIn("reject work that prohibits AI", plan.acceptance_tests)
        self.assertIn("three consecutive cycles", plan.stop_rule)
        self.assertEqual(plan.fixture_opportunity_ids, ("market-doc-1",))

        backlog = enrich_capability_backlog({"items": []}, clusters, plans)
        self.assertEqual(backlog["capability_market_engine"], "active")
        self.assertEqual(backlog["capability_market_plan_count"], 1)
        item = backlog["items"][0]
        self.assertEqual(item["capability_market_rank"], 1)
        self.assertEqual(item["execution_priority"], "cash_first")
        self.assertIn("Simulation values are planning signals only", item["issue"]["body"])


if __name__ == "__main__":
    unittest.main()
