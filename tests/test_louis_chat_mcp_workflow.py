from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy-louis-chat.yml"
).read_text(encoding="utf-8")


class LouisChatMcpWorkflowTests(unittest.TestCase):
    def test_bridge_changes_trigger_chat_deployment(self):
        self.assertIn('"atlas/louis_mcp.py"', WORKFLOW)

    def test_smoke_rejects_anonymous_mcp_and_verifies_tools(self):
        self.assertIn('[[ "${ANON_CODE}" == "401" ]]', WORKFLOW)
        self.assertIn('.result.serverInfo.name == "louis-os-mentor"', WORKFLOW)
        self.assertIn(".result.tools | length == 4", WORKFLOW)

    def test_pairing_token_is_not_printed_or_persisted(self):
        self.assertIn('TOKEN="$(jq -er', WORKFLOW)
        self.assertNotIn("echo ${TOKEN}", WORKFLOW)
        self.assertNotIn("http_headers", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
