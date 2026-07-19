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


if __name__ == "__main__":
    unittest.main()
