from __future__ import annotations

import unittest
from pathlib import Path

from atlas.internet_opportunity_router import infer_domain, next_pivot, route
from scripts.internet_opportunity_router_cycle import build_cycle, extract_items, normalize_candidate


class InternetOpportunityRouterTests(unittest.TestCase):
    def test_execute_now_for_verified_csv_mission(self) -> None:
        result = route({
            "title": "Urgent CSV cleanup and deduplication",
            "description": "Normalize columns and deliver a cleaned CSV",
            "capability_fit": 0.95,
            "effort_hours": 3,
            "fresh_open_verified": True,
            "payment_path": "fixed-price milestone",
            "acceptance_criteria": ["clean file", "duplicate report"],
            "legal_policy_pass": True,
            "human_actions_required": 0,
            "reward_eur": 90,
            "payment_confidence": 0.9,
            "competition_risk": 0.2,
        })
        self.assertEqual(result.domain, "data_csv")
        self.assertEqual(result.lane, "exploit")
        self.assertEqual(result.decision, "execute_now")
        self.assertGreater(result.score, 0)

    def test_prepare_then_gate_for_one_account_action(self) -> None:
        result = route({
            "title": "Fix one API webhook",
            "description": "Reproduce, patch and test an API integration",
            "capability_fit": 0.90,
            "effort_hours": 5,
            "fresh_open_verified": True,
            "payment_path": "platform milestone",
            "acceptance_criteria": ["test passes"],
            "legal_policy_pass": True,
            "human_actions_required": 1,
            "reward_eur": 150,
            "payment_confidence": 0.8,
        })
        self.assertEqual(result.decision, "prepare_then_gate")

    def test_rejects_personal_language_eligibility(self) -> None:
        result = route({
            "title": "Native interpreter needed",
            "description": "Live legal interpretation",
            "fresh_open_verified": True,
            "payment_path": "milestone",
            "acceptance_criteria": ["live attendance"],
            "legal_policy_pass": True,
            "personal_eligibility_required": True,
            "effort_hours": 4,
        })
        self.assertEqual(result.decision, "reject")
        self.assertIn("personal_eligibility_required", result.reasons)

    def test_capability_build_requires_verified_market_signal(self) -> None:
        result = route({
            "title": "Create a small digital template",
            "description": "Reusable Notion template",
            "capability_fit": 0.5,
            "effort_hours": 6,
            "fresh_open_verified": True,
            "payment_path": "marketplace payout",
            "acceptance_criteria": ["template delivered"],
            "legal_policy_pass": True,
            "market_signal_verified": True,
        })
        self.assertEqual(result.decision, "capability_build")

    def test_pivot_rules(self) -> None:
        self.assertEqual(next_pivot({"rejected_without_candidate": 30}), "regenerate_queries_and_shift_domain")
        self.assertEqual(next_pivot({"source_results_without_eligible": 50}), "pause_source_and_replace")
        self.assertEqual(next_pivot({"proposals_without_reply": 5}), "change_offer_or_message")
        self.assertEqual(next_pivot({"verified_payments": 1}), "expand_similar_searches")

    def test_normalizes_upstream_market_schema(self) -> None:
        item = normalize_candidate({
            "title": "Small API fix",
            "canonical_url": "https://example.test/job",
            "estimated_effort_hours": 4,
            "reward_amount": 120,
            "payment_methods": ["milestone"],
            "metadata": {"official_source": True, "status_verified_open": True},
            "deliverables": ["tested patch"],
            "capability_fit": 0.9,
        }, "catalog.json")
        self.assertEqual(item["effort_hours"], 4.0)
        self.assertEqual(item["payment_path"], "milestone")
        self.assertTrue(item["fresh_open_verified"])
        self.assertTrue(item["legal_policy_pass"])
        self.assertEqual(item["source_file"], "catalog.json")

    def test_normalizes_official_agent_native_open_job(self) -> None:
        item = normalize_candidate({
            "opportunity_id": "agent-job-1",
            "title": "Build one Python parser",
            "description": "Implement parser.py and make the supplied assertions pass.",
            "source_url": "https://market.example/jobs/1",
            "observed_at": "2026-08-27T12:00:00+00:00",
            "reward_amount": 8,
            "reward_verified": True,
            "payment_evidence": ["https://market.example/jobs?status=open", "escrow=funded"],
            "account_required": True,
            "decision": {"status": "prepare_then_gate"},
            "metadata": {
                "source_kind": "agent_native_public_api",
                "official_source": True,
                "days_left": 3,
                "estimated_effort_hours": 2,
            },
        }, "market.json")
        self.assertTrue(item["fresh_open_verified"])
        self.assertTrue(item["acceptance_criteria"])
        self.assertEqual(item["capability_fit"], 0.9)
        self.assertEqual(route(item).decision, "prepare_then_gate")

    def test_does_not_promote_unfunded_agent_need_as_open_job(self) -> None:
        item = normalize_candidate({
            "opportunity_id": "unfunded-1",
            "title": "Need an API pipeline",
            "description": "Buyer may fund later.",
            "source_url": "https://market.example/needs/1",
            "observed_at": "2026-08-27T12:00:00+00:00",
            "reward_amount": 25,
            "reward_verified": False,
            "metadata": {
                "source_kind": "agent_to_agent_public_api",
                "official_source": True,
                "market_stage": "unfunded_need",
                "days_left": 3,
            },
        }, "market.json")
        self.assertFalse(item["fresh_open_verified"])
        self.assertEqual(route(item).decision, "reject")

    def test_does_not_resurrect_an_upstream_policy_rejection(self) -> None:
        item = normalize_candidate({
            "opportunity_id": "policy-rejected-1",
            "title": "Personal financial advice",
            "description": "Personalized investment portfolio and asset allocation.",
            "source_url": "https://market.example/jobs/rejected",
            "observed_at": "2026-08-28T12:00:00+00:00",
            "reward_amount": 100,
            "reward_verified": True,
            "payment_evidence": ["official reward"],
            "account_required": True,
            "decision": {"status": "rejected"},
            "metadata": {
                "source_kind": "public_freelance_listing",
                "official_source": True,
                "days_left": 3,
                "estimated_effort_hours": 2,
            },
        }, "market.json")
        result = route(item)
        self.assertEqual(result.decision, "reject")
        self.assertIn("upstream_rejected", result.reasons)

    def test_rejects_unsafe_raw_feed_before_upstream_classification(self) -> None:
        result = route({
            "title": "Financial consulting",
            "description": "Build a personalized investment portfolio and asset allocation.",
            "skills": ["Investment Management"],
            "capability_fit": 0.9,
            "effort_hours": 2,
            "fresh_open_verified": True,
            "payment_path": "milestone",
            "acceptance_criteria": ["portfolio"],
            "legal_policy_pass": True,
            "human_actions_required": 1,
            "reward_eur": 100,
            "payment_confidence": 0.9,
        })
        self.assertEqual(result.decision, "reject")
        self.assertIn(
            "policy_rejected:regulated_personalized_financial_advice",
            result.reasons,
        )

    def test_extracts_multiple_catalogs_and_deduplicates(self) -> None:
        payloads = [
            ("a.json", {"opportunities": [
                {"opportunity_id": "1", "title": "CSV cleanup"},
                {"opportunity_id": "2", "title": "API fix"},
            ]}),
            ("b.json", {"candidates": [
                {"opportunity_id": "2", "title": "API fix", "description": "richer description"},
                {"opportunity_id": "3", "title": "Research brief"},
            ]}),
        ]
        items = extract_items(payloads)
        self.assertEqual(len(items), 3)
        api = next(item for item in items if item["opportunity_id"] == "2")
        self.assertEqual(api["description"], "richer description")

    def test_extracts_sources_fairly_when_first_catalog_is_large(self) -> None:
        payloads = [
            ("large.json", {"opportunities": [
                {"opportunity_id": f"large-{index}", "source_id": "large-source", "title": f"Task {index}"}
                for index in range(100)
            ]}),
            ("later.json", {"opportunities": [
                {"opportunity_id": "molt-1", "source_id": "moltjobs_agent_jobs", "title": "Later funded job"}
            ]}),
        ]
        items = extract_items(payloads)
        self.assertIn("moltjobs_agent_jobs", {item["source_id"] for item in items})
        self.assertLessEqual(sum(item["source_id"] == "large-source" for item in items), 20)

    def test_cycle_reports_source_and_domain_breadth(self) -> None:
        payloads = [
            ("catalog-a.json", {"opportunities": [{
                "opportunity_id": "csv-1",
                "title": "CSV cleanup",
                "description": "deduplicate spreadsheet data",
                "capability_fit": 0.95,
                "effort_hours": 3,
                "fresh_open_verified": True,
                "payment_path": "milestone",
                "acceptance_criteria": ["clean CSV"],
                "legal_policy_pass": True,
                "reward_eur": 90,
                "payment_confidence": 0.9,
            }]}),
            ("catalog-b.json", {"opportunities": [{
                "opportunity_id": "web-1",
                "title": "Landing page form fix",
                "description": "repair responsive frontend form",
                "capability_fit": 0.8,
                "effort_hours": 4,
                "fresh_open_verified": True,
                "payment_path": "fixed price",
                "acceptance_criteria": ["form submits"],
                "legal_policy_pass": True,
                "reward_eur": 100,
                "payment_confidence": 0.8,
            }]}),
        ]
        cycle = build_cycle(payloads)
        self.assertEqual(cycle["items_seen"], 2)
        self.assertEqual(cycle["sources_seen"], 2)
        self.assertGreaterEqual(cycle["domains_seen"], 2)
        self.assertEqual(cycle["schema_version"], "1.2")

    def test_required_capability_overrides_incidental_description_keywords(self) -> None:
        domain, fit = infer_domain({
            "title": "Investment research brief",
            "description": "The final report includes a responsive form appendix.",
            "required_capabilities": ["evidence_research_dossier"],
        })
        self.assertEqual(domain, "b2b_research")
        self.assertEqual(fit, 1.0)

    def test_cycle_honors_tested_canonical_cash_first_selection(self) -> None:
        def candidate(opportunity_id: str, reward: float, prepared: bool) -> dict:
            return {
                "opportunity_id": opportunity_id,
                "source_id": "test-market",
                "title": "Build one Python server",
                "description": "Implement and test a bounded Python socket server.",
                "required_capabilities": ["python_automation_delivery"],
                "estimated_effort_hours": 2,
                "reward_amount": reward,
                "reward_verified": True,
                "payment_evidence": ["official funded reward"],
                "payment_methods": ["USDC"],
                "account_required": True,
                "decision": {"status": "prepare_then_gate"},
                "metadata": {
                    "source_kind": "agent_native_public_api",
                    "official_source": True,
                    "days_left": 3,
                    "submission_dossier_prepared": prepared,
                },
                "observed_at": "2026-08-28T12:00:00+00:00",
            }

        canonical = candidate("cash-top", 8, True)
        higher_router_score = candidate("other", 80, False)
        cycle = build_cycle([
            ("catalog.json", {"opportunities": [higher_router_score, canonical]}),
            ("cash_first_market.json", {"top_cash_first": {"opportunity_id": "cash-top"}}),
        ])
        self.assertEqual(cycle["selected"]["opportunity_id"], "cash-top")
        self.assertEqual(cycle["selection_source"], "canonical_cash_first")
        self.assertEqual(
            cycle["next_action"],
            "request exact platform account and terms gate for tested deliverable",
        )

    def test_workflow_reports_only_meaningful_changes_without_blocking_routing(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "internet-opportunity-router.yml").read_text()
        self.assertIn("meaningful_changed", workflow)
        self.assertIn("gh issue comment 141", workflow)
        self.assertNotIn("gh issue comment 77", workflow)
        self.assertIn("routing and persistence succeeded", workflow)


if __name__ == "__main__":
    unittest.main()
