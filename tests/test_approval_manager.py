from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def load_module(name: str, relative_path: str):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, root / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


approval_manager = load_module("approval_manager", "scripts/autonomous_approval_manager.py")
executor = load_module("opportunity_executor", "scripts/autonomous_opportunity_executor.py")


def executable_candidate(candidate_id: str = "0123456789abcdef") -> dict:
    return {
        "id": candidate_id,
        "title": "Paid documentation fix",
        "url": "https://github.com/example/project/issues/12",
        "score": 75,
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
    }


class ApprovalManagerTests(unittest.TestCase):
    def test_top_resolves_to_first_candidate(self):
        candidates = [{"id": "0123456789abcdef"}, {"id": "fedcba9876543210"}]
        self.assertEqual(
            approval_manager.resolve_candidate("top", candidates),
            "0123456789abcdef",
        )

    def test_unconsumed_approval_is_selected(self):
        store = {
            "approvals": [
                {"candidate_id": "0123456789abcdef", "status": "approved", "consumed_at": None}
            ]
        }
        approval = executor.find_approval(store, "0123456789abcdef")
        self.assertIsNotNone(approval)

    def test_consumed_approval_is_not_reused(self):
        store = {
            "approvals": [
                {
                    "candidate_id": "0123456789abcdef",
                    "status": "approved",
                    "consumed_at": "2026-07-19T00:00:00+00:00",
                }
            ]
        }
        self.assertIsNone(executor.find_approval(store, "0123456789abcdef"))

    def test_executable_candidate_starts_without_redundant_internal_approval(self):
        candidate = executable_candidate()
        self.assertEqual(
            executor.internal_authorization_mode(candidate, None),
            "autonomous_executable_candidate",
        )
        _, body = executor.build_issue(candidate)
        self.assertIn("autonomous_executable_candidate", body)
        self.assertIn("external prerequisites are cleared", body)

    def test_existing_explicit_approval_remains_valid_evidence(self):
        candidate = executable_candidate()
        approval = {
            "candidate_id": candidate["id"],
            "status": "approved",
            "source_issue": 77,
            "source_comment_id": 123,
            "approved_by": "owner",
            "consumed_at": None,
        }
        self.assertEqual(
            executor.internal_authorization_mode(candidate, approval),
            "explicit_owner_approval",
        )
        _, body = executor.build_issue(candidate, approval)
        self.assertIn("Approval source: issue #77 comment `123`", body)

    def test_gated_candidate_cannot_use_autonomous_internal_authorization(self):
        candidate = executable_candidate()
        candidate["readiness_status"] = "gated_external_prerequisite"
        candidate["external_prerequisites_cleared"] = False
        with self.assertRaisesRegex(ValueError, "candidate_not_executable"):
            executor.internal_authorization_mode(candidate, None)


if __name__ == "__main__":
    unittest.main()
