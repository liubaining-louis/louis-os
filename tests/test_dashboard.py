import unittest

from atlas.dashboard import DASHBOARD_HTML


class DashboardTests(unittest.TestCase):
    def test_dashboard_contains_core_sections(self):
        self.assertIn("Louis OS", DASHBOARD_HTML)
        self.assertIn("Centre de contrôle", DASHBOARD_HTML)
        self.assertIn("Nouvelle mission", DASHBOARD_HTML)
        self.assertIn("Mémoire", DASHBOARD_HTML)

    def test_dashboard_uses_same_origin_api(self):
        self.assertIn("/health", DASHBOARD_HTML)
        self.assertIn("/missions", DASHBOARD_HTML)
        self.assertIn("/memories", DASHBOARD_HTML)
        self.assertIn("credentials='same-origin'", DASHBOARD_HTML)

    def test_dashboard_does_not_request_or_store_api_key(self):
        self.assertNotIn("X-Louis-Key", DASHBOARD_HTML)
        self.assertNotIn("louisKey", DASHBOARD_HTML)
        self.assertNotIn("apiKey", DASHBOARD_HTML)
        self.assertIn("Aucun code ni clé API", DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
