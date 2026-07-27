from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UniversalMarketWorkflowTests(unittest.TestCase):
    def test_workflow_runs_canonical_capability_market_cycle(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        self.assertIn('"requests/universal-market-cycle.json"', text)
        self.assertIn("python scripts/universal_market_cycle.py", text)
        self.assertIn("python scripts/refresh_small_bounty_sources.py", text)
        self.assertIn("python scripts/verify_small_bounty_issue_state.py", text)
        self.assertIn("python scripts/refresh_simple_mission_sources.py", text)
        self.assertIn("python scripts/enforce_delivery_compatibility.py", text)
        self.assertIn("python scripts/capability_market_cycle.py", text)
        self.assertIn("python scripts/prepare_simple_mission_dossiers.py", text)
        self.assertIn("python scripts/cash_first_market_postprocess.py", text)
        self.assertIn("python scripts/sync_cash_first_ledger.py", text)
        self.assertIn("python scripts/create_capability_gap_issues.py", text)
        self.assertIn("python -m unittest tests.test_small_bounty_sources -v", text)
        self.assertIn("python -m unittest tests.test_github_issue_verifier -v", text)
        self.assertIn("python -m unittest tests.test_simple_mission_sources -v", text)
        self.assertIn("python -m unittest tests.test_guru_simple_mission_source -v", text)
        self.assertIn("python -m unittest tests.test_truelancer_simple_mission_source -v", text)
        self.assertIn("python -m unittest tests.test_capability_market -v", text)
        self.assertIn("python -m unittest tests.test_cash_first_ledger_sync -v", text)
        for path in (
            "results/universal_market_opportunities.json",
            "results/small_bounty_source_refresh.json",
            "results/simple_mission_source_refresh.json",
            "results/delivery_compatibility_receipt.json",
            "results/capability_market.json",
            "results/mission_clusters.json",
            "results/revenue_simulation.json",
            "results/capability_build_plan.json",
            "results/capability_market_history.json",
            "results/cluster_proposal_templates",
            "results/simple_mission_dossier_receipts.json",
            "results/simple_mission_dossiers",
            "results/cash_first_market.json",
            "results/human_action_required.json",
            "results/monetization.json",
            "results/capability_issue_receipts.json",
        ):
            self.assertIn(path, text)
        self.assertIn("gh issue comment 77", text)
        self.assertIn("gh issue comment 141", text)
        self.assertIn("gh issue comment 192", text)

    def test_compatibility_and_capability_market_precede_routing(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        refresh_bounties = text.index("python scripts/refresh_small_bounty_sources.py")
        verify_canonical = text.index("python scripts/verify_small_bounty_issue_state.py")
        refresh_simple = text.index("python scripts/refresh_simple_mission_sources.py")
        compatibility = text.index("python scripts/enforce_delivery_compatibility.py")
        capability_market = text.index("python scripts/capability_market_cycle.py")
        prepare_dossiers = text.index("python scripts/prepare_simple_mission_dossiers.py")
        rank_cash = text.index("python scripts/cash_first_market_postprocess.py")
        sync_ledger = text.index("python scripts/sync_cash_first_ledger.py")
        self.assertLess(refresh_bounties, verify_canonical)
        self.assertLess(verify_canonical, refresh_simple)
        self.assertLess(refresh_simple, compatibility)
        self.assertLess(compatibility, capability_market)
        self.assertLess(capability_market, prepare_dossiers)
        self.assertLess(prepare_dossiers, rank_cash)
        self.assertLess(rank_cash, sync_ledger)

    def test_manual_request_envelope_is_cash_first_and_truthful(self) -> None:
        request = json.loads((ROOT / "requests/universal-market-cycle.json").read_text(encoding="utf-8"))
        self.assertTrue(request["execute_now"])
        self.assertEqual(request["master_issue"], 77)
        self.assertEqual(request["priority"]["lane"], "cash_first")
        self.assertLessEqual(request["priority"]["ideal_effort_hours_max"], 16)
        self.assertLessEqual(request["priority"]["ideal_time_to_cash_days_max"], 30)
        self.assertTrue(request["constraints"]["exclude_charcoal"])
        self.assertTrue(request["constraints"]["no_fabricated_revenue"])
        self.assertTrue(request["constraints"]["no_fabricated_submission"])
        self.assertTrue(request["constraints"]["no_fabricated_evidence"])
        self.assertIn("results/cash_first_market.json", request["required_outputs"])
        self.assertIn("results/human_action_required.json", request["required_outputs"])
        self.assertIn("results/monetization.json", request["required_outputs"])

    def test_universal_workflow_commits_ledger_atomically(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        self.assertNotIn("git restore --worktree --staged results/monetization.json", text)
        self.assertIn("group: monetization-ledger-writer", text)
        persistence = text.split("for path in", 1)[1].split("; do", 1)[0]
        self.assertIn("results/monetization.json", persistence)
        autonomous = (ROOT / ".github/workflows/autonomous-tested-submission.yml").read_text(encoding="utf-8")
        self.assertIn("group: monetization-ledger-writer", autonomous)

    def test_standalone_verifier_is_manual_recovery_only(self) -> None:
        text = (ROOT / ".github/workflows/verify-bounty-issue-state.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("workflow_run:", text)
        self.assertIn("group: monetization-ledger-writer", text)
        self.assertIn("python scripts/verify_small_bounty_issue_state.py", text)
        self.assertIn("python scripts/cash_first_market_postprocess.py", text)
        self.assertIn("python scripts/sync_cash_first_ledger.py", text)
        self.assertIn("results/monetization.json", text)

    def test_dedicated_ledger_workflow_remains_recovery_path(self) -> None:
        text = (ROOT / ".github/workflows/cash-first-ledger-sync.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/sync_cash_first_ledger.py", text)
        self.assertIn("python -m unittest tests.test_cash_first_ledger_sync -v", text)
        self.assertIn("results/monetization.json", text)
        self.assertIn("group: monetization-ledger-writer", text)

    def test_prompt_requires_market_clustering_and_truthful_revenue(self) -> None:
        text = (ROOT / "docs/prompts/UNIVERSAL_MARKET_MONETIZATION.md").read_text(encoding="utf-8")
        self.assertIn("Pour une opportunité rentable hors capacité", text)
        self.assertIn("créer automatiquement une fiche de capacité bornée", text)
        self.assertIn("regrouper les missions similaires", text)
        self.assertIn("simulation", text.casefold())
        self.assertIn("Ne jamais déclarer une soumission, un contrat ou un revenu sans reçu vérifiable", text)
        self.assertIn("ne contourne pas les contrôles d’accès", text)
        self.assertIn("cash_first", text)

    def test_source_catalog_covers_multiple_market_categories(self) -> None:
        text = (ROOT / "config/universal_market_sources.json").read_text(encoding="utf-8")
        for source in (
            "github_bounties",
            "opire_public_bounties",
            "algora_public_bounties",
            "freelancer_public_simple_jobs",
            "guru_public_simple_jobs",
            "truelancer_public_simple_jobs",
            "user_interviews_participant_studies",
            "respondent_participant_studies",
            "testingtime_participant_studies",
            "usagov_challenges",
            "upwork_marketplace",
            "kaggle_competitions",
            "hackerone_programs",
            "sam_contract_opportunities",
        ):
            self.assertIn(source, text)

    def test_public_marketplace_adapters_are_in_the_refresh_mesh(self) -> None:
        text = (ROOT / "scripts/refresh_simple_mission_sources.py").read_text(encoding="utf-8")
        self.assertIn("FreelancerPublicJobsSource", text)
        self.assertIn("GuruPublicJobsSource", text)
        self.assertIn("TruelancerPublicJobsSource", text)
        catalog = (ROOT / "config/universal_market_sources.json").read_text(encoding="utf-8")
        self.assertIn("freelancer_public_simple_jobs", catalog)
        self.assertIn("guru_public_simple_jobs", catalog)
        self.assertIn("truelancer_public_simple_jobs", catalog)


if __name__ == "__main__":
    unittest.main()
