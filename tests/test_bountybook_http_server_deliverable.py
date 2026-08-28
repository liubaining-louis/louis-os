from __future__ import annotations

import http.client
import importlib.util
from pathlib import Path
import sys
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
DELIVERABLE = ROOT / "deliverables" / "bountybook_http_server_19a16071" / "http_server.py"
SPEC = importlib.util.spec_from_file_location("bountybook_http_server", DELIVERABLE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
HTTPServer = MODULE.HTTPServer
Response = MODULE.Response


class BountyBookHTTPServerDeliverableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HTTPServer("127.0.0.1", 0)

        @self.server.route("/ping")
        def ping(_request):
            return Response(200, "text/plain", "pong")

        @self.server.route("/echo", method="POST")
        def echo(request):
            return Response(200, "application/json", f'{{"body": "{request.body}"}}')

        @self.server.route("/unicode")
        def unicode_body(_request):
            return Response(200, "text/plain; charset=utf-8", "été")

        self.thread = threading.Thread(target=lambda: self.server.start(timeout=5), daemon=True)
        self.thread.start()
        self.assertTrue(self.server.wait_until_ready(1))

    def tearDown(self) -> None:
        self.server.stop()
        self.thread.join(1)

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=2)
        connection.request(method, path, body=body)
        response = connection.getresponse()
        payload = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, payload

    def test_get_post_and_missing_route(self) -> None:
        status, headers, body = self.request("GET", "/ping")
        self.assertEqual((status, body), (200, b"pong"))
        self.assertEqual(headers["Connection"], "close")

        status, _, body = self.request("POST", "/echo", body="hello")
        self.assertEqual(status, 200)
        self.assertIn(b"hello", body)

        status, _, body = self.request("GET", "/missing")
        self.assertEqual((status, body), (404, b"Not Found"))

    def test_content_length_counts_encoded_bytes_and_query_routes(self) -> None:
        status, headers, body = self.request("GET", "/unicode?source=test")
        self.assertEqual(status, 200)
        self.assertEqual(body.decode("utf-8"), "été")
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_deliverable_uses_only_allowed_modules(self) -> None:
        source = DELIVERABLE.read_text(encoding="utf-8")
        for forbidden in ("http.server", "socketserver", "asyncio", "requests"):
            self.assertNotIn(forbidden, source)
        imported = {
            line.split()[1].split(".")[0]
            for line in source.splitlines()
            if line.startswith("import ")
        }
        self.assertEqual(imported, {"socket", "threading", "re"})


if __name__ == "__main__":
    unittest.main()
