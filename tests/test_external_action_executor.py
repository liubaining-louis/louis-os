import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "autonomous_external_action_executor.py"
spec = importlib.util.spec_from_file_location("external_executor", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def ready_action():
    return {
        "id": "action-1",
        "candidate_id": "0123456789abcdef",
        "type": "github_issue_comment",
        "target_url": "https://github.com/example/project/issues/12",
        "body": "Tested submission",
        "status": "ready",
        "tested_deliverable": True,
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
        "evidence": ["https://github.com/example/project/actions/runs/1"],
    }


class ExternalActionExecutorTests(unittest.TestCase):
    def test_valid_ready_action(self):
        self.assertEqual(module.validate_action(ready_action()), (True, "ok"))

    def test_refuses_untested_action(self):
        action = ready_action()
        action["tested_deliverable"] = False
        self.assertEqual(module.validate_action(action), (False, "deliverable_not_tested"))

    def test_refuses_missing_evidence(self):
        action = ready_action()
        action["evidence"] = []
        self.assertEqual(module.validate_action(action), (False, "missing_evidence"))

    def test_refuses_uncleared_external_prerequisites(self):
        action = ready_action()
        action["external_prerequisites_cleared"] = False
        self.assertEqual(
            module.validate_action(action),
            (False, "external_prerequisites_not_cleared"),
        )

    def test_refuses_non_github_target(self):
        action = ready_action()
        action["target_url"] = "https://example.com/submit"
        self.assertEqual(module.validate_action(action), (False, "unsupported_target"))

    def test_external_approval_consumed_once(self):
        store = {
            "approvals": [
                {
                    "candidate_id": "0123456789abcdef",
                    "status": "approved",
                    "scope": "external_submission",
                    "consumed_at": None,
                }
            ]
        }
        approval = module.find_external_approval(store, "0123456789abcdef")
        self.assertIsNotNone(approval)
        approval["consumed_at"] = "now"
        self.assertIsNone(module.find_external_approval(store, "0123456789abcdef"))
