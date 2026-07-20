from __future__ import annotations

import unittest

from atlas.autonomous_action_bridge import (
    cancel_active_actions,
    github_approval_target,
    is_explicit_github_approval,
    queue_approved_action,
    stop_action_id,
)


class FakeDocument:
    def __init__(self, document_id, payload):
        self.id = document_id
        self.payload = dict(payload)
        self.reference = self

    def to_dict(self):
        return dict(self.payload)

    def set(self, values, merge=False):
        if merge:
            self.payload.update(values)
        else:
            self.payload = dict(values)


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents
        self.session_id = None

    def where(self, field, operator, value):
        if (field, operator) != ("session_id", "=="):
            raise AssertionError("unexpected query")
        self.session_id = value
        return self

    def stream(self):
        return [doc for doc in self.documents.values() if doc.payload.get("session_id") == self.session_id]

    def document(self, document_id):
        return self.documents.setdefault(document_id, FakeDocument(document_id, {}))


class FakeFirestore:
    def __init__(self, actions):
        self.collections = {
            "louis_action_queue": FakeCollection({item.id: item for item in actions}),
            "louis_runtime": FakeCollection({"current": FakeDocument("current", {})}),
        }

    def collection(self, name):
        return self.collections[name]


class AutonomousActionBridgeIntentTests(unittest.TestCase):
    def test_accepts_only_canonical_candidate_confirmation(self):
        command = "AUTORISER GITHUB 0fac76fc8abf3e9e"
        self.assertTrue(is_explicit_github_approval(command))
        self.assertEqual(github_approval_target(command), "0fac76fc8abf3e9e")

    def test_accepts_only_canonical_issue_url_confirmation(self):
        url = "https://github.com/example/project/issues/42"
        self.assertEqual(github_approval_target(f"AUTORISER GITHUB {url}"), url)

    def test_audit_and_negation_are_never_approvals(self):
        messages = (
            "Audit d'autonomie : quelles actions exigent une autorisation GitHub ?",
            "Ceci n'est pas une autorisation GitHub.",
            "Ne lance aucune action GitHub.",
            "ok, fais un statut GitHub",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertFalse(is_explicit_github_approval(message))

    def test_stop_is_prioritary_and_can_target_one_action(self):
        action_id = "66a2cd2a5ef14158b6767a3397d7ac0a"
        self.assertEqual(stop_action_id("STOP / RÉVOCATION immédiate"), "*")
        self.assertEqual(stop_action_id(f"annule action {action_id}"), action_id)
        self.assertIsNone(stop_action_id("Quel est le statut des actions ?"))

    def test_approval_must_match_the_current_candidate(self):
        state = {"top_candidate": {"id": "0fac76fc8abf3e9e", "url": "https://github.com/a/b/issues/1"}}
        with self.assertRaisesRegex(ValueError, "approval_target_does_not_match"):
            queue_approved_action(
                None,
                session_id="s1",
                message="AUTORISER GITHUB f00f9474a19725ba",
                state=state,
            )

    def test_stop_cancels_all_non_terminal_actions_in_the_session(self):
        active = FakeDocument("a" * 32, {"session_id": "s1", "status": "implementation_planning"})
        ready = FakeDocument("b" * 32, {"session_id": "s1", "status": "approved_ready"})
        completed = FakeDocument("c" * 32, {"session_id": "s1", "status": "completed"})
        other = FakeDocument("d" * 32, {"session_id": "s2", "status": "approved_ready"})
        db = FakeFirestore([active, ready, completed, other])

        cancelled = cancel_active_actions(db, session_id="s1", message="STOP", action_id="*")

        self.assertEqual(cancelled, ["a" * 32, "b" * 32])
        self.assertEqual(active.payload["status"], "cancelled")
        self.assertEqual(ready.payload["status"], "cancelled")
        self.assertEqual(completed.payload["status"], "completed")
        self.assertEqual(other.payload["status"], "approved_ready")
        runtime = db.collection("louis_runtime").document("current").payload
        self.assertTrue(runtime["waiting_for_instruction"])
        self.assertIsNone(runtime["active_action_id"])


if __name__ == "__main__":
    unittest.main()
