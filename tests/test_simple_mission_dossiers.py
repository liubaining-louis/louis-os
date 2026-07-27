from __future__ import annotations

import unittest

from scripts.prepare_simple_mission_dossiers import build_proposal, platform_gate_instruction


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

    def test_uses_exact_truelancer_security_gate_instruction(self) -> None:
        exact = (
            "Authorize use of a truthful Truelancer account and review/accept the platform terms so Louis OS can submit the prepared proposal. "
            "Keep all payment on-platform; never pay a security deposit."
        )
        opportunity = {
            "source_id": "truelancer_public_simple_jobs",
            "metadata": {
                "platform": "Truelancer",
                "platform_gate_instruction": exact,
            },
        }
        self.assertEqual(platform_gate_instruction(opportunity), exact)

    def test_falls_back_to_truthful_generic_gate(self) -> None:
        opportunity = {
            "source_id": "guru_public_simple_jobs",
            "metadata": {"platform": "Guru"},
        }
        instruction = platform_gate_instruction(opportunity)
        self.assertIn("truthful Guru account", instruction)
        self.assertIn("Do not complete KYC", instruction)


if __name__ == "__main__":
    unittest.main()
