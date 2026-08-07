from __future__ import annotations

import unittest
from unittest.mock import patch

from atlas.multi_model_monetization import candidate_fingerprint, run_team_review
from atlas.providers import ModelResponse


class MultiModelMonetizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = [{
            "id": "c1",
            "title": "Build an API demo",
            "execution_score": 0.91,
            "score": 0.88,
            "reward_amount": 250,
            "currency": "USDC",
            "readiness_status": "executable_now",
            "acceptance_criteria": ["working demo", "README"],
            "payment_path": "USDC",
        }]

    def test_fingerprint_is_stable_and_changes_with_artifact(self) -> None:
        a = candidate_fingerprint(self.candidates, "aaa")
        b = candidate_fingerprint(self.candidates, "aaa")
        c = candidate_fingerprint(self.candidates, "bbb")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    @patch("atlas.multi_model_monetization.complete_with")
    def test_fast_then_reasoning_then_critic(self, complete_with) -> None:
        complete_with.side_effect = [
            ModelResponse("groq", "llama", '{"selected_candidate_id":"c1","shortlist_ids":["c1"],"reject_ids":[],"rationale":"fit","estimated_hours":2,"risk_flags":[]}'),
            ModelResponse("vertex", "gemini", '{"recommendation":"execute_now","acceptance_criteria":["working demo","README"],"missing_information":[],"payment_path_verified":true,"submission_channel_verified":true,"risk_flags":[],"execution_plan":["build","test","submit"]}'),
            ModelResponse("vertex", "gemini", '{"critic_pass":false,"defects":["minor wording"],"unmet_acceptance_criteria":[],"evidence_gaps":[],"revision_instructions":["tighten README"]}'),
            ModelResponse("vertex", "gemini", '{"revised_plan":["tighten README","submit"],"remaining_blockers":[],"recommendation":"prepare_then_gate","submission_safe":true}'),
        ]
        result = run_team_review(self.candidates)
        self.assertEqual(result.selected_candidate_id, "c1")
        self.assertEqual(result.fast_provider, "groq")
        self.assertEqual(result.reasoning_provider, "vertex")
        self.assertFalse(result.critic_pass)
        self.assertTrue(result.revision_required)
        self.assertEqual(complete_with.call_count, 4)

    @patch("atlas.multi_model_monetization.complete_with")
    def test_critic_does_not_claim_external_submission(self, complete_with) -> None:
        complete_with.side_effect = [
            ModelResponse("groq", "llama", '{"selected_candidate_id":"c1","shortlist_ids":["c1"],"reject_ids":[],"rationale":"fit","estimated_hours":2,"risk_flags":[]}'),
            ModelResponse("vertex", "gemini", '{"recommendation":"execute_now","acceptance_criteria":[],"missing_information":[],"payment_path_verified":true,"submission_channel_verified":true,"risk_flags":[],"execution_plan":[]}'),
            ModelResponse("vertex", "gemini", '{"critic_pass":true,"defects":[],"unmet_acceptance_criteria":[],"evidence_gaps":[],"revision_instructions":[]}'),
        ]
        result = run_team_review(self.candidates)
        self.assertTrue(result.critic_pass)
        self.assertNotIn("externally_submitted", result.raw)
        self.assertNotIn("revenue", result.raw)


if __name__ == "__main__":
    unittest.main()
