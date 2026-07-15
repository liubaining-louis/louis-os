import unittest
from unittest.mock import patch

from atlas.providers import _request_headers


class ProviderHeaderTests(unittest.TestCase):
    def test_explicit_user_agent_and_accept_headers(self):
        headers = _request_headers("secret-value", "groq")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertTrue(headers["User-Agent"].startswith("LouisOS/"))
        self.assertEqual(headers["Authorization"], "Bearer secret-value")
        self.assertNotIn("secret-value", headers["User-Agent"])

    def test_openrouter_metadata_headers(self):
        headers = _request_headers("secret-value", "openrouter")
        self.assertIn("HTTP-Referer", headers)
        self.assertEqual(headers["X-Title"], "Louis OS")

    def test_other_provider_does_not_receive_openrouter_headers(self):
        headers = _request_headers("secret-value", "groq")
        self.assertNotIn("HTTP-Referer", headers)
        self.assertNotIn("X-Title", headers)


if __name__ == "__main__":
    unittest.main()
