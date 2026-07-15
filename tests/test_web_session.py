import os
import unittest
from unittest.mock import patch

from atlas.web_session import (
    build_set_cookie_header,
    create_session_token,
    token_from_cookie_header,
    validate_session_token,
)


class WebSessionTests(unittest.TestCase):
    def test_signed_session_is_valid_until_expiry(self):
        with patch.dict(os.environ, {"LOUIS_OS_API_KEY": "test-secret", "WEB_SESSION_TTL_SECONDS": "600"}, clear=False):
            token = create_session_token(now=1_000)
            self.assertTrue(validate_session_token(token, now=1_500))
            self.assertFalse(validate_session_token(token, now=1_601))

    def test_tampered_session_is_rejected(self):
        with patch.dict(os.environ, {"LOUIS_OS_API_KEY": "test-secret"}, clear=False):
            token = create_session_token(now=1_000)
            self.assertFalse(validate_session_token(token + "x", now=1_001))

    def test_cookie_is_secure_and_http_only(self):
        with patch.dict(os.environ, {"LOUIS_OS_API_KEY": "test-secret"}, clear=False):
            header = build_set_cookie_header(now=1_000)
            self.assertIn("HttpOnly", header)
            self.assertIn("Secure", header)
            self.assertIn("SameSite=Strict", header)
            token = token_from_cookie_header(header.split(";", 1)[0])
            self.assertTrue(validate_session_token(token, now=1_001))


if __name__ == "__main__":
    unittest.main()
