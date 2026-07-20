from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"
).read_text(encoding="utf-8")


class DeploySecurityWorkflowTests(unittest.TestCase):
    def test_production_smoke_blocks_anonymous_session_issuance(self):
        self.assertIn("Public root must not issue an authenticated session", WORKFLOW)
        self.assertIn("^set-cookie: louis_session=", WORKFLOW)

    def test_production_smoke_requires_401_for_protected_route(self):
        self.assertIn('"${SERVICE_URL}/missions?limit=1"', WORKFLOW)
        self.assertIn('"${ANON_CODE}" != "401"', WORKFLOW)


if __name__ == "__main__":
    unittest.main()
