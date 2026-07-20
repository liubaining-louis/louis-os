from __future__ import annotations

from http.server import ThreadingHTTPServer
import os
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from atlas.server import AtlasHandler


class ServerAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {"LOUIS_OS_API_KEY": "test-secret"}, clear=False)
        self.environment.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AtlasHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.environment.stop()

    def test_public_root_does_not_issue_session(self) -> None:
        with urlopen(f"{self.base}/", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Set-Cookie"))

    def test_protected_route_rejects_anonymous_request(self) -> None:
        with self.assertRaises(HTTPError) as captured:
            urlopen(f"{self.base}/missions?limit=1", timeout=2)
        self.assertEqual(captured.exception.code, 401)

    def test_session_requires_valid_explicit_key(self) -> None:
        invalid = Request(f"{self.base}/session", data=b"", method="POST", headers={"X-Louis-Key": "wrong"})
        with self.assertRaises(HTTPError) as captured:
            urlopen(invalid, timeout=2)
        self.assertEqual(captured.exception.code, 401)

        valid = Request(
            f"{self.base}/session",
            data=b"",
            method="POST",
            headers={"X-Louis-Key": "test-secret"},
        )
        with urlopen(valid, timeout=2) as response:
            cookie = response.headers.get("Set-Cookie")
        self.assertIn("louis_session=", cookie)
        self.assertIn("HttpOnly", cookie)

        authorized = Request(f"{self.base}/not-found", headers={"Cookie": cookie.split(";", 1)[0]})
        with self.assertRaises(HTTPError) as accepted:
            urlopen(authorized, timeout=2)
        self.assertEqual(accepted.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
