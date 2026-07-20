from http.server import ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from atlas import louis_chat_v6 as chat
from atlas.louis_mcp import MemoryMentorBridgeStore, MentorBridge


class LouisChatMcpHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        bridge = MentorBridge(
            MemoryMentorBridgeStore(),
            history=lambda session_id, limit: [{"role": "user", "text": "history"}],
            louis_reply=lambda session_id, message: f"Louis says {message}",
        )
        self.mentor_patch = patch.object(chat, "_mentor", bridge)
        self.mentor_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), chat.Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"
        pairing = self.request("/v1/codex/pair", {}, expected=201)
        self.token = pairing["token"]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.mentor_patch.stop()

    def request(self, path, payload=None, token=None, expected=200, origin=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if origin:
            headers["Origin"] = origin
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=body, headers=headers, method="POST" if payload is not None else "GET")
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, expected)
            data = response.read()
        return json.loads(data) if data else {}

    def test_mcp_requires_pairing(self):
        request = Request(
            self.base + "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as captured:
            urlopen(request, timeout=3)
        self.assertEqual(captured.exception.code, 401)
        self.assertEqual(captured.exception.headers.get("WWW-Authenticate"), "Bearer")

    def test_mcp_initialize_and_tools(self):
        initialized = self.request(
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            token=self.token,
        )
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "louis-os-mentor")
        tools = self.request(
            "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, token=self.token
        )
        self.assertEqual(len(tools["result"]["tools"]), 4)

    def test_chat_to_codex_queue_and_reply(self):
        queued = self.request("/v1/codex/messages", {"message": "analyse ceci"}, token=self.token, expected=201)
        pending = self.request(
            "/mcp",
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_pending_mentor_messages", "arguments": {}}},
            token=self.token,
        )
        self.assertEqual(pending["result"]["structuredContent"]["messages"][0]["message_id"], queued["message_id"])
        self.request(
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "reply_to_mentor_message", "arguments": {"message_id": queued["message_id"], "reply": "réponse mentor"}},
            },
            token=self.token,
        )
        messages = self.request("/v1/codex/messages", token=self.token)
        self.assertEqual(messages["messages"][0]["reply"], "réponse mentor")

    def test_cross_origin_mcp_request_is_rejected(self):
        request = Request(
            self.base + "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}", "Origin": "https://evil.example"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as captured:
            urlopen(request, timeout=3)
        self.assertEqual(captured.exception.code, 403)

    def test_page_exposes_pairing_without_embedded_token(self):
        with urlopen(self.base + "/", timeout=3) as response:
            page = response.read().decode()
        self.assertIn("Connecter Codex", page)
        self.assertIn("/v1/codex/pair", page)
        self.assertNotIn(self.token, page)


if __name__ == "__main__":
    unittest.main()
