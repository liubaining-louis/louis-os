from __future__ import annotations

import unittest

from atlas.opportunity_factory import (
    TARGET_ALLOCATION,
    allocation_plan,
    build_factory_plan,
    build_query_pack,
    capability_registry,
    classify_rejection,
    diagnose_funnel,
)


class OpportunityFactoryTests(unittest.TestCase):
    def test_unknown_is_not_terminal_bad(self) -> None:
        self.assertEqual(classify_rejection("payment_evidence_missing"), "unknown")
        self.assertEqual(classify_rejection("acceptance_criteria_missing"), "unknown")
        self.assertEqual(classify_rejection("platform_policy_blocked"), "bad")

    def test_detects_tiny_market_perception(self) -> None:
        issues = diagnose_funnel({
            "scout_items_inspected": 120,
            "universal_market_opportunities_observed": 11,
            "simple_mission_dossiers_prepared": 0,
        })
        self.assertEqual(issues[0].stage, "discovery")
        self.assertEqual(issues[0].severity, "critical")

    def test_allocation_never_collapses_to_experimental_only(self) -> None:
        plan = allocation_plan({"capability_experiments": 1.0})
        self.assertEqual(plan["target"], TARGET_ALLOCATION)
        self.assertGreater(plan["delta"]["explicit_marketplaces"], 0)
        self.assertGreater(plan["delta"]["proactive_problem_discovery"], 0)
        self.assertLess(plan["delta"]["capability_experiments"], 0)

    def test_registry_expands_micro_capabilities(self) -> None:
        registry = capability_registry(["python_script", "static_website"])
        self.assertGreaterEqual(registry["target_count"], 35)
        self.assertIn("contact_form_fix", registry["missing"])
        self.assertIn("csv_cleanup", registry["missing"])

    def test_query_pack_contains_multiple_lanes(self) -> None:
        pack = build_query_pack(["csv_cleanup", "contact_form_fix"], maximum=30)
        lanes = {item["lane"] for item in pack}
        self.assertIn("explicit_marketplaces", lanes)
        self.assertIn("public_requests", lanes)
        self.assertIn("proactive_problem_discovery", lanes)

    def test_factory_sets_economic_floor_and_volume_targets(self) -> None:
        plan = build_factory_plan({
            "scout_items_inspected": 120,
            "universal_market_opportunities_observed": 11,
            "external_actions_submitted": 0,
            "revenue_confirmed_eur": 0,
        }, current_allocation={"capability_experiments": 1.0})
        self.assertEqual(plan["economic_floor"]["minimum_hourly_value"], 8.0)
        self.assertEqual(plan["cycle_targets"]["signals_seen_min"], 1000)
        self.assertEqual(plan["cycle_targets"]["verified_external_actions_target_when_valid_candidate_exists"], 1)
        self.assertTrue(plan["truth"]["plan_is_not_submission"])


if __name__ == "__main__":
    unittest.main()
