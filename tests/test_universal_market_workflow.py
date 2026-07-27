from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UniversalMarketWorkflowTests(unittest.TestCase):
    def test_workflow_runs_non_github_market_cycle_and_capability_loop(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        self.assertIn('"requests/universal-market-cycle.json"', text)
        self.assertIn("python scripts/universal_market_cycle.py", text)
        self.assertIn("python scripts/refresh_small_bounty_sources.py", text)
        self.assertIn("python scripts/cash_first_market_postprocess.py", text)
        self.assertIn("python scripts/create_capability_gap_issues.py", text)
        self.assertIn("python -m unittest tests.test_small_bounty_sources -v", text)
        self.assertIn("results/universal_market_opportunities.json", text)
        self.assertIn("results/small_bounty_source_refresh.json", text)
        self.assertIn("results/cash_first_market.json", text)
        self.assertIn("results/human_action_required.json", text)
        self.assertIn("results/capability_issue_receipts.json", text)
        self.assertIn("gh issue comment 77", text)
        self.assertIn("gh issue comment 141", text)
        self.assertIn("gh issue comment 170", text)
        self.assertIn("gh issue comment 176", text)

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

    def test_workflow_does_not_commit_shared_monetization_ledger(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        self.assertIn("git restore --worktree --staged results/monetization.json", text)
        persistence = text.split("for path in", 1)[1].split("; do", 1)[0]
        self.assertNotIn("results/monetization.json", persistence)

    def test_prompt_requires_capability_acquisition_and_truthful_revenue(self) -> None:
        text = (ROOT / "docs/prompts/UNIVERSAL_MARKET_MONETIZATION.md").read_text(encoding="utf-8")
        self.assertIn("Pour une opportunité rentable hors capacité", text)
        self.assertIn("créer automatiquement une fiche de capacité bornée", text)
        self.assertIn("Ne jamais déclarer une soumission, un contrat ou un revenu sans reçu vérifiable", text)
        self.assertIn("ne contourne pas les contrôles d’accès", text)
        self.assertIn("cash_first", text)

    def test_source_catalog_covers_multiple_market_categories(self) -> None:
        text = (ROOT / "config/universal_market_sources.json").read_text(encoding="utf-8")
        for source in (
            "github_bounties",
            "opire_public_bounties",
            "algora_public_bounties",
            "usagov_challenges",
            "upwork_marketplace",
            "kaggle_competitions",
            "hackerone_programs",
            "sam_contract_opportunities",
        ):
            self.assertIn(source, text)


if __name__ == "__main__":
    unittest.main()
