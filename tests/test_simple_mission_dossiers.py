from __future__ import annotations

import unittest

from scripts.prepare_simple_mission_dossiers import build_proposal


class SimpleMissionDossierTests(unittest.TestCase):
    def test_builds_platform_neutral_guru_quote_dossier(self) -> None:
        opportunity = {
            "source_id": "guru_public_simple_jobs",
            "source_url": "https://www.guru.com/jobs/example/123",
            "title": "Verified public company research",
            "description": "Research public official websites and deliver a sourced spreadsheet.",
            "reward_amount": 50.0,
            "currency": "USD",
            "required_capabilities": ["evidence_research_dossier"],
            "metadata": {
                "platform": "Guru",
                "budget_kind": "fixed_range",
                "budget_min": 50.0,
                "estimated_effort_hours": 8.0,
            },
        }
        dossier = build_proposal(opportunity)
        self.assertIn("Platform: Guru", dossier)
        self.assertIn("Conservative proposed quote: 50 USD", dossier)
        self.assertIn("public authoritative sources", dossier)
        self.assertIn("External submission: false", dossier)
        self.assertIn("payment-protection mechanism", dossier)

    def test_builds_spreadsheet_validation_controls(self) -> None:
        opportunity = {
            "source_id": "guru_public_simple_jobs",
            "source_url": "https://www.guru.com/jobs/example/124",
            "title": "Excel cleanup",
            "description": "Clean a supplied workbook.",
            "reward_amount": 80.0,
            "currency": "USD",
            "required_capabilities": ["python_data_analysis"],
            "metadata": {
                "platform": "Guru",
                "budget_kind": "hourly_range",
                "budget_min": 10.0,
                "estimated_effort_hours": 8.0,
            },
        }
        dossier = build_proposal(opportunity)
        self.assertIn("validate row counts, formulas, types and output schema", dossier)
        self.assertIn("Budget basis: hourly_range", dossier)


if __name__ == "__main__":
    unittest.main()
