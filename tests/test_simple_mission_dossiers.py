from __future__ import annotations

import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from scripts import prepare_simple_mission_dossiers as preparation

from scripts.prepare_simple_mission_dossiers import build_proposal, platform_gate_instruction


class DossierProductionGateTests(unittest.TestCase):
    def run_preparation(self, effort=12.0, reward=132.0, policy_updates=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            policy = json.loads((preparation.ROOT / "config/production_policy.json").read_text())
            policy.update(policy_updates or {})
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(policy))
            market_path = results / "market.json"
            dossier_root = results / "simple_mission_dossiers"
            proposal_path = "results/simple_mission_dossiers/market-45c0d728fc509a87/proposal.md"
            stale_proposal = root / proposal_path
            stale_proposal.parent.mkdir(parents=True)
            stale_proposal.write_text("old unsubmitted proposal")
            opportunity = {
                "opportunity_id": "market-45c0d728fc509a87",
                "title": "Modernise Kernow Roast Co. Website",
                "description": "Modernise navigation, product pages, calculators and quote forms.",
                "reward_amount": reward, "reward_verified": True, "currency": "USD",
                "required_capabilities": ["static_website_delivery"],
                "decision": {"status": "prepare_then_gate"},
                "evidence": ["https://www.freelancer.com/projects/website-design/modernise-kernow-roast-website", proposal_path],
                "metadata": {
                    "source_kind": "public_freelance_listing", "platform": "Freelancer.com",
                    "estimated_effort_hours": effort, "submission_dossier_required": True,
                    "submission_dossier_prepared": True, "proposal_path": proposal_path,
                    "proposal_sha256": "stale", "proposal_manifest_path": "stale",
                    "human_action_instructions": ["stale account request"],
                },
            }
            market_path.write_text(json.dumps({"opportunities": [opportunity]}))
            replacements = {
                "ROOT": root, "RESULTS": results, "MARKET_PATH": market_path,
                "CYCLE_PATH": results / "cycle.json", "DOSSIERS_ROOT": dossier_root,
                "RECEIPT_PATH": results / "receipts.json",
            }
            with patch.multiple(preparation, **replacements), patch.object(preparation, "POLICY_PATH", policy_path):
                preparation.main()
            return (json.loads(market_path.read_text())["opportunities"][0],
                    json.loads((results / "receipts.json").read_text()),
                    list(dossier_root.rglob("proposal.md")),
                    json.loads((results / "cycle.json").read_text()))

    def test_real_twelve_hour_listing_is_blocked_before_dossier_and_account_gate(self):
        opportunity, receipt, proposals, cycle = self.run_preparation()
        self.assertEqual(receipt["prepared_count"], 0)
        self.assertEqual(proposals, [])
        self.assertEqual(receipt["blocked"][0]["reason"], "effort_exceeds_quick_win_limit")
        metadata = opportunity["metadata"]
        self.assertFalse(metadata["submission_dossier_prepared"])
        for key in ("proposal_path", "proposal_sha256", "proposal_manifest_path", "human_action_instructions"):
            self.assertNotIn(key, metadata)
        self.assertFalse(any(x.startswith("results/simple_mission_dossiers/") for x in opportunity["evidence"]))
        self.assertEqual(cycle["next_action"], "review_production_policy_rejections")

    def test_three_hour_boundary_still_prepares_without_external_submission(self):
        _, receipt, proposals, _ = self.run_preparation(effort=3)
        self.assertEqual(receipt["prepared_count"], 1)
        self.assertEqual(len(proposals), 1)
        self.assertFalse(receipt["receipts"][0]["externally_submitted"])

    def test_unknown_effort_stays_visible_without_default_eight_hour_proposal(self):
        opportunity, receipt, proposals, _ = self.run_preparation(effort=None)
        self.assertEqual(receipt["prepared_count"], 0)
        self.assertEqual(proposals, [])
        self.assertEqual(opportunity["metadata"]["dossier_preparation_blocked"], "effort_estimate_unknown")

    def test_existing_reward_and_kill_switch_guards_apply_before_preparation(self):
        for args, reason in [({"effort": 2, "reward": 501}, "reward_exceeds_quick_win_strategy_cap"),
                             ({"effort": 2, "policy_updates": {"kill_switch": True}}, "global_kill_switch_active"),
                             ({"effort": "invalid"}, "invalid_effort_estimate")]:
            with self.subTest(reason=reason):
                _, receipt, proposals, _ = self.run_preparation(**args)
                self.assertEqual(receipt["prepared_count"], 0)
                self.assertEqual(proposals, [])
                self.assertEqual(receipt["blocked"][0]["reason"], reason)


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

    def test_builds_static_website_implementation_dossier(self) -> None:
        opportunity = {
            "source_id": "freelancer_public_software_jobs",
            "source_url": "https://www.freelancer.com/projects/html/example",
            "title": "Responsive landing page",
            "description": "Build one responsive HTML and CSS landing page with supplied content.",
            "reward_amount": 250.0,
            "currency": "EUR",
            "required_capabilities": ["static_website_delivery"],
            "metadata": {
                "platform": "Freelancer.com",
                "budget_kind": "fixed_range",
                "budget_min": 250.0,
                "estimated_effort_hours": 8.0,
                "software_boundaries": ["maximum one static page", "no authentication or payment processing"],
                "software_acceptance_checks": ["all local assets resolve"],
            },
        }
        dossier = build_proposal(opportunity)
        self.assertIn("build dependency-free semantic HTML", dossier)
        self.assertIn("validate semantic HTML, local assets, local links", dossier)
        self.assertIn("maximum one static page", dossier)
        self.assertIn("no authentication or payment processing", dossier)
        self.assertIn("External submission: false", dossier)

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
