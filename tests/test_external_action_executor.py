import importlib.util
from pathlib import Path

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
        "evidence": ["https://github.com/example/project/actions/runs/1"],
    }


def test_valid_ready_action():
    assert module.validate_action(ready_action()) == (True, "ok")


def test_refuses_untested_action():
    action = ready_action()
    action["tested_deliverable"] = False
    assert module.validate_action(action) == (False, "deliverable_not_tested")


def test_refuses_missing_evidence():
    action = ready_action()
    action["evidence"] = []
    assert module.validate_action(action) == (False, "missing_evidence")


def test_refuses_non_github_target():
    action = ready_action()
    action["target_url"] = "https://example.com/submit"
    assert module.validate_action(action) == (False, "unsupported_target")


def test_external_approval_consumed_once():
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
    assert approval is not None
    approval["consumed_at"] = "now"
    assert module.find_external_approval(store, "0123456789abcdef") is None
