import unittest
from unittest.mock import patch

from atlas import louis_state


class LouisStateInitiativePolicyTests(unittest.TestCase):
    def test_policy_forbids_permission_loop(self):
        policy = louis_state._response_policy()

        self.assertEqual(policy["mode"], "initiative_first_result_driven")
        self.assertIn(
            "Que souhaites-tu que je fasse exactement ?",
            policy["forbidden_response_patterns"],
        )
        self.assertIn(
            "choose and start the best low-risk reversible action without asking what to do",
            policy["default_behavior"],
        )

    @patch("atlas.louis_state._count_jsonl", return_value=0)
    @patch("atlas.louis_state._read_json", return_value={})
    @patch("atlas.louis_state._runtime_state")
    def test_snapshot_exposes_live_autonomy_state(self, runtime, _read_json, _count_jsonl):
        runtime.return_value = {
            "worker_verified": True,
            "autonomy_policy": "result_first_autonomy",
            "waiting_for_instruction": False,
            "human_gate_pending": False,
            "requires_user_validation": False,
            "external_actions_submitted": 1,
            "external_receipts_verified": 1,
            "execution_status": "external_action_verified",
            "next_action": "Track response independently.",
            "synced_at": "2026-07-20T21:00:00+00:00",
        }

        state = louis_state.snapshot()
        worker = state["autonomous_worker"]

        self.assertEqual(worker["policy_mode"], "result_first_autonomy")
        self.assertFalse(worker["waiting_for_instruction"])
        self.assertFalse(worker["human_gate_pending"])
        self.assertFalse(worker["requires_user_validation"])
        self.assertEqual(worker["actions_submitted"], 1)
        self.assertNotIn("première action externe réellement soumise", state["not_yet_verified"])
        self.assertNotIn("premier reçu vérifiable d'exécution externe", state["not_yet_verified"])

    @patch("atlas.louis_state._count_jsonl", return_value=0)
    @patch("atlas.louis_state._read_json", return_value={})
    @patch("atlas.louis_state._runtime_state", return_value={"worker_verified": True})
    def test_missing_capability_does_not_default_to_waiting_for_user(
        self, _runtime, _read_json, _count_jsonl
    ):
        state = louis_state.snapshot()

        self.assertFalse(state["autonomous_worker"]["waiting_for_instruction"])
        self.assertEqual(
            state["autonomous_worker"]["next_action"],
            "Infer and execute the next safe, reversible step.",
        )
        self.assertIn(
            "une limite de capacité déclenche une stratégie alternative ou une tâche d'implémentation, pas une demande vague à l'utilisateur",
            state["guardrails"],
        )


if __name__ == "__main__":
    unittest.main()
