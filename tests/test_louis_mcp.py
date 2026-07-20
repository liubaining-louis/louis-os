import unittest
from unittest.mock import patch

from atlas.louis_mcp import MemoryMentorBridgeStore, MentorBridge, bearer_token, token_hash


class LouisMcpBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryMentorBridgeStore()
        self.history = {}
        self.bridge = MentorBridge(
            self.store,
            history=lambda session_id, limit: self.history.get(session_id, [])[-limit:],
            louis_reply=lambda session_id, message: f"Louis:{session_id}:{message}",
        )
        self.pairing = self.bridge.create_pairing()
        self.token = self.pairing["token"]
        self.session_id = self.pairing["session_id"]
        self.history[self.session_id] = [{"role": "user", "text": "bonjour"}]

    def rpc(self, method, params=None, request_id=1):
        return self.bridge.rpc(
            self.token,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
        )

    def test_pairing_stores_only_token_digest(self):
        self.assertNotIn(self.token, self.store.pairings)
        self.assertIn(token_hash(self.token), self.store.pairings)
        self.assertGreaterEqual(len(self.token), 32)

    def test_bearer_parser_rejects_short_or_wrong_scheme(self):
        self.assertEqual(bearer_token(None), "")
        self.assertEqual(bearer_token("Basic abc"), "")
        self.assertEqual(bearer_token("Bearer short"), "")
        self.assertEqual(bearer_token(f"Bearer {self.token}"), self.token)

    def test_pairings_are_isolated(self):
        second = self.bridge.create_pairing()
        queued = self.bridge.queue(self.token, "question A")
        self.assertEqual(queued["session_id"], self.session_id)
        self.assertEqual(self.bridge.messages(second["token"]), [])

    def test_reply_is_idempotent_but_conflicting_rewrite_is_blocked(self):
        queued = self.bridge.queue(self.token, "question")
        digest = token_hash(self.token)
        first = self.store.reply_message(digest, queued["message_id"], "réponse", "2026-01-01T00:00:00+00:00")
        second = self.store.reply_message(digest, queued["message_id"], "réponse", "2026-01-01T00:01:00+00:00")
        self.assertEqual(first["reply"], second["reply"])
        with self.assertRaisesRegex(ValueError, "message_already_replied"):
            self.store.reply_message(digest, queued["message_id"], "autre", "2026-01-01T00:02:00+00:00")

    def test_initialize_and_tools_follow_mcp_contract(self):
        initialized = self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "louis-os-mentor")
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "get_louis_chat_history",
                "send_message_to_louis",
                "list_pending_mentor_messages",
                "reply_to_mentor_message",
            ],
        )
        self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
        self.assertFalse(tools[3]["annotations"]["destructiveHint"])

    def test_mcp_tools_round_trip(self):
        history = self.rpc("tools/call", {"name": "get_louis_chat_history", "arguments": {}})
        self.assertEqual(history["result"]["structuredContent"]["messages"][0]["text"], "bonjour")
        louis = self.rpc(
            "tools/call", {"name": "send_message_to_louis", "arguments": {"message": "statut ?"}}
        )
        self.assertEqual(
            louis["result"]["structuredContent"]["reply"], f"Louis:{self.session_id}:statut ?"
        )
        queued = self.bridge.queue(self.token, "aide-moi")
        pending = self.rpc("tools/call", {"name": "list_pending_mentor_messages", "arguments": {}})
        self.assertEqual(pending["result"]["structuredContent"]["messages"][0]["message_id"], queued["message_id"])
        replied = self.rpc(
            "tools/call",
            {
                "name": "reply_to_mentor_message",
                "arguments": {"message_id": queued["message_id"], "reply": "voici"},
            },
        )
        self.assertEqual(replied["result"]["structuredContent"]["status"], "replied")

    def test_expired_pairing_is_rejected(self):
        digest = token_hash(self.token)
        self.store.pairings[digest]["expires_at"] = "2000-01-01T00:00:00+00:00"
        with self.assertRaises(PermissionError):
            self.bridge.resolve(self.token)

    def test_pairing_ttl_is_bounded_when_configuration_is_invalid(self):
        with patch.dict("os.environ", {"LOUIS_CODEX_PAIRING_TTL_DAYS": "invalid"}):
            value = self.bridge.create_pairing()
        self.assertIn("expires_at", value)


if __name__ == "__main__":
    unittest.main()
