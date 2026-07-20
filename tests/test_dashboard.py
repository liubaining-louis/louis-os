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

    def test_dashboard_exchanges_key_without_persisting_it(self):
        self.assertIn("/session", DASHBOARD_HTML)
        self.assertIn("X-Louis-Key", DASHBOARD_HTML)
        self.assertNotIn("localStorage", DASHBOARD_HTML)
        self.assertNotIn("sessionStorage", DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
