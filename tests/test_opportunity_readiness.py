import importlib.util
from pathlib import Path
import unittest

from atlas.opportunity_readiness import assess_opportunity_readiness, candidate_is_executable


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OpportunityReadinessTests(unittest.TestCase):
    def test_signup_and_maintainer_confirmation_make_bounty_gated(self):
        result = assess_opportunity_readiness(
            {
                "title": "Paid bounty",
                "body": "Sign up as a developer. Do not start until a maintainer confirms your claim.",
            },
            80.0,
        )
        self.assertEqual(result.status, "gated_external_prerequisite")
        self.assertIn("third_party_account_required", result.external_prerequisites)
        self.assertIn("maintainer_confirmation_required", result.external_prerequisites)
        self.assertLess(result.execution_score, 80.0)

    def test_claim_phrase_and_confirmation_before_work_are_gated(self):
        result = assess_opportunity_readiness(
            {
                "title": "Email Threads API bounty",
                "body": (
                    "Return to this issue and comment: I have signed up and would like to claim this bounty. "
                    "A maintainer must confirm before work begins."
                ),
            },
            80.0,
        )
        self.assertEqual(result.status, "gated_external_prerequisite")
        self.assertIn("third_party_account_required", result.external_prerequisites)
        self.assertIn("application_or_claim_required", result.external_prerequisites)
        self.assertIn("maintainer_confirmation_required", result.external_prerequisites)

    def test_fee_terms_and_contract_are_gated(self):
        result = assess_opportunity_readiness(
            {
                "title": "Technical competition",
                "body": "Registration fee required. Winners must sign an agreement and accept the terms.",
            },
            90.0,
        )
        self.assertEqual(result.status, "gated_external_prerequisite")
        self.assertIn("payment_or_fee_required", result.external_prerequisites)
        self.assertIn("external_terms_or_contract_required", result.external_prerequisites)

    def test_plain_public_issue_is_executable(self):
        result = assess_opportunity_readiness(
            {"title": "Paid documentation fix", "body": "Submit a tested patch to this public repository."},
            65.0,
        )
        self.assertEqual(result.status, "executable_now")
        self.assertEqual(result.execution_score, 65.0)
        candidate = {
            "readiness_status": result.status,
            "external_prerequisites_cleared": result.executable_now,
        }
        self.assertTrue(candidate_is_executable(candidate))

    def test_missing_readiness_metadata_fails_closed(self):
        self.assertFalse(candidate_is_executable({"score": 100.0}))

    def test_internal_executor_skips_attractive_but_gated_candidate(self):
        module = _load_script("autonomous_opportunity_executor.py")
        self.assertFalse(
            module.candidate_is_executable(
                {
                    "readiness_status": "gated_external_prerequisite",
                    "external_prerequisites_cleared": False,
                }
            )
        )
