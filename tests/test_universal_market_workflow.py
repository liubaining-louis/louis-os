from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UniversalMarketWorkflowTests(unittest.TestCase):
    def test_workflow_runs_non_github_market_cycle_and_capability_loop(self) -> None:
        text = (ROOT / ".github/workflows/universal-market-monetization.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/universal_market_cycle.py", text)
        self.assertIn("python scripts/create_capability_gap_issues.py", text)
        self.assertIn("results/universal_market_opportunities.json", text)
        self.assertIn("results/capability_issue_receipts.json", text)
        self.assertIn("gh issue comment 77", text)
        self.assertIn("gh issue comment 141", text)

    def test_prompt_requires_capability_acquisition_and_truthful_revenue(self) -> None:
        text = (ROOT / "docs/prompts/UNIVERSAL_MARKET_MONETIZATION.md").read_text(encoding="utf-8")
        self.assertIn("Pour une opportunité rentable hors capacité", text)
        self.assertIn("créer automatiquement une fiche de capacité bornée", text)
        self.assertIn("Ne jamais déclarer une soumission, un contrat ou un revenu sans reçu vérifiable", text)
        self.assertIn("ne contourne pas les contrôles d’accès", text)

    def test_source_catalog_covers_multiple_market_categories(self) -> None:
        text = (ROOT / "config/universal_market_sources.json").read_text(encoding="utf-8")
        for source in (
            "github_bounties",
            "usagov_challenges",
            "upwork_marketplace",
            "kaggle_competitions",
            "hackerone_programs",
            "sam_contract_opportunities",
        ):
            self.assertIn(source, text)


if __name__ == "__main__":
    unittest.main()
