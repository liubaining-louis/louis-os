from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import threading
import time
import unittest

from deliverables.automation_pilot.automation import MAX_BYTES, process, webhook_handler
from deliverables.automation_pilot.chatbot_qa import evaluate, report

FIXTURE = Path(__file__).resolve().parents[1] / "deliverables/automation_pilot/chatbot_cases.json"


@contextmanager
def running_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def mock_handler(status=200, body=b'{"status":"received","ticket_id":"DEMO-001","private":"not returned"}', delay=0):
    class MockAPI(BaseHTTPRequestHandler):
        calls = 0

        def log_message(self, *_args):
            pass

        def do_POST(self):
            type(self).calls += 1
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            time.sleep(delay)
            self.send_response(status)
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass
    return MockAPI


class AutomationSalesPilotTests(unittest.TestCase):
    body = b'{"request_id":"DEMO-1","category":"support","message":"Fictional test only"}'

    def test_real_loopback_webhook_to_rest_roundtrip(self):
        mock = mock_handler()
        with running_server(mock) as upstream:
            endpoint = f"http://127.0.0.1:{upstream.server_port}/mock"
            with running_server(webhook_handler(endpoint)) as front:
                connection = http.client.HTTPConnection("127.0.0.1", front.server_port, timeout=2)
                connection.request("POST", "/webhook", self.body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), {"ok": True, "request_id": "DEMO-1", "ticket_id": "DEMO-001", "status": "received"})
                connection.close()
        self.assertEqual(mock.calls, 1)

    def test_invalid_inputs_do_not_call_api(self):
        for body in (b"not json", b"[]", b"{}", b"\xff", b'{"request_id":false,"category":"sales","message":"test"}', self.body.replace(b"support", b"unknown")):
            with self.subTest(body=body):
                self.assertEqual(process(body, "not-an-endpoint")[0], 400)

    def test_oversize_input_is_rejected(self):
        self.assertEqual(process(b"x" * (MAX_BYTES + 1), "not-an-endpoint")[0], 413)

    def test_production_destinations_are_refused(self):
        for url in ("https://example.com/mock", "http://localhost:123/mock", "http://127.0.0.1:123/mock?next=external", "http://user@127.0.0.1:123/mock", "http://[broken", "http://127.0.0.1:bad/mock"):
            self.assertEqual(process(self.body, url)[1]["error"]["code"], "demo_endpoint_not_allowed")

    def test_upstream_errors_and_redirects_are_not_retried(self):
        for status in (302, 401, 429, 500):
            with self.subTest(status=status):
                mock = mock_handler(status=status)
                with running_server(mock) as server:
                    code, body = process(self.body, f"http://127.0.0.1:{server.server_port}/mock")
                self.assertEqual(code, 502)
                self.assertFalse(body["automatic_retry"])
                self.assertEqual(mock.calls, 1)

    def test_invalid_upstream_outputs_are_explicit(self):
        for raw, error in ((b"broken", "upstream_invalid_json"), (b"[]", "upstream_invalid_schema"), (b"{}", "upstream_invalid_schema"), (b"x" * (MAX_BYTES + 1), "upstream_response_too_large")):
            with self.subTest(error=error):
                with running_server(mock_handler(body=raw)) as server:
                    code, body = process(self.body, f"http://127.0.0.1:{server.server_port}/mock")
                self.assertEqual(code, 502)
                self.assertEqual(body["error"]["code"], error)

    def test_timeout_is_visible_without_retry(self):
        mock = mock_handler(delay=0.1)
        with running_server(mock) as server:
            code, body = process(self.body, f"http://127.0.0.1:{server.server_port}/mock", timeout=0.02)
        self.assertEqual(code, 504)
        self.assertEqual(body["error"]["code"], "upstream_timeout")
        self.assertEqual(mock.calls, 1)

    def test_live_webhook_rejects_wrong_path_and_content_type(self):
        with running_server(webhook_handler("not-used")) as front:
            for path, content, expected in (("/wrong", "application/json", 404), ("/webhook", "text/plain", 415)):
                connection = http.client.HTTPConnection("127.0.0.1", front.server_port, timeout=2)
                connection.request("POST", path, self.body, {"Content-Type": content})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()


class ChatbotPilotTests(unittest.TestCase):
    def test_twelve_synthetic_cases_detect_exactly_six_seeded_faults(self):
        result = report(FIXTURE)
        self.assertEqual(result["cases"], 12)
        self.assertEqual(result["flagged"], 6)
        self.assertTrue(result["manual_semantic_and_language_review_required"])
        for row in result["results"]:
            self.assertEqual(bool(row["issues"]), "seeded-fault" in row["case_id"])
        self.assertFalse(result["payment_verified"])

    def test_invalid_response_cannot_pass(self):
        self.assertEqual(evaluate({"response": None, "expected": {}}, set()), ["invalid_response_schema"])

    def test_string_false_cannot_pass_escalation_check(self):
        case = {"response": {"answer": "test", "source_ids": [], "escalate": "false", "action_taken": "none"}, "expected": {"escalate": False}}
        self.assertIn("escalation_mismatch", evaluate(case, set()))

    def test_unknown_source_is_not_a_verified_citation(self):
        case = {"response": {"answer": "test", "source_ids": ["invented"], "escalate": False, "action_taken": "none"}, "expected": {"escalate": False}}
        self.assertIn("unknown_or_invalid_source", evaluate(case, {"real"}))
