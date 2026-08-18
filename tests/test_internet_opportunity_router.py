from __future__ import annotations

import unittest

from atlas.internet_opportunity_router import next_pivot, route
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

    def test_preserves_verified_personal_eligibility_rejection(self) -> None:
        item = normalize_candidate({
            "title": "Native German Audio Recording Session",
            "description": "Only native speakers from Germany may participate.",
            "fresh_open_verified": True,
            "reward_amount": 30,
            "payment_methods": ["platform milestone"],
            "deliverables": ["one-hour German recording"],
            "capability_fit": 0.9,
            "estimated_effort_hours": 2,
            "decision": {
                "status": "rejected",
                "blockers": ["unverifiable_personal_eligibility"],
            },
            "metadata": {
                "official_source": True,
                "policy_rejection": "unverifiable_personal_eligibility",
                "policy_rejection_verified": True,
            },
        }, "universal_market_opportunities.json")

        self.assertTrue(item["personal_eligibility_required"])
        result = route(item)
        self.assertEqual(result.decision, "reject")
        self.assertIn("personal_eligibility_required", result.reasons)

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


if __name__ == "__main__":
    unittest.main()
