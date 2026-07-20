import unittest
from unittest.mock import patch

from scripts import sync_operational_state_to_firestore as sync


class OperationalStateSyncTests(unittest.TestCase):
    def test_gated_candidate_is_not_projected_as_executable(self):
        gated = {
            "id": "abc",
            "title": "Candidate",
            "readiness_status": "gated_external_prerequisite",
            "external_prerequisites_cleared": False,
            "external_prerequisites": ["third_party_account_required"],
        }
        fixtures = {
            "monetization.json": {"top_opportunity": None},
            "monetization_candidates.json": {"count": 1, "candidates": [gated]},
            "external_action_queue.json": {"actions": []},
            "external_action_receipts.json": {"receipts": []},
        }
        with patch.object(sync, "load_json", side_effect=lambda name, default: fixtures.get(name, default)):
            state = sync.build_operational_state("2026-07-19T20:00:00+00:00")

        self.assertIsNone(state["top_candidate"])
        self.assertEqual(state["opportunities_executable"], 0)
        self.assertEqual(state["opportunities_gated"], 1)
        sanitized = sync.sanitize_candidate(gated)
        self.assertTrue(sanitized["manual_validation_required"])
        self.assertIn("third_party_account_required", sanitized["manual_validation_reasons"])

    def test_executable_candidate_is_projected(self):
        executable = {
            "id": "safe",
            "readiness_status": "executable_now",
            "external_prerequisites_cleared": True,
        }
        fixtures = {
            "monetization.json": {"top_opportunity": executable},
            "monetization_candidates.json": {"count": 1, "candidates": [executable]},
            "external_action_queue.json": {"actions": []},
            "external_action_receipts.json": {"receipts": []},
        }
        with patch.object(sync, "load_json", side_effect=lambda name, default: fixtures.get(name, default)):
            state = sync.build_operational_state("2026-07-19T20:00:00+00:00")

        self.assertEqual(state["top_candidate"]["id"], "safe")
        self.assertFalse(state["top_candidate"]["manual_validation_required"])
        self.assertEqual(state["opportunities_executable"], 1)

    def test_verified_receipt_has_priority(self):
        fixtures = {
            "monetization.json": {},
            "monetization_candidates.json": {"count": 0, "candidates": []},
            "external_action_queue.json": {"actions": []},
            "external_action_receipts.json": {
                "receipts": [{"action_id": "a1", "verified": True, "receipt_url": "https://github.com/x"}]
            },
        }
        with patch.object(sync, "load_json", side_effect=lambda name, default: fixtures.get(name, default)):
            state = sync.build_operational_state("2026-07-19T20:00:00+00:00")

        self.assertEqual(state["execution_status"], "external_action_verified")
        self.assertEqual(state["external_receipts_verified"], 1)


if __name__ == "__main__":
    unittest.main()
