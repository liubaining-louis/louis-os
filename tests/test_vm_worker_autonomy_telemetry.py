from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.vm_monetization_worker import recent_autonomy_failures


class RecentAutonomyFailuresTests(unittest.TestCase):
    def test_returns_latest_failed_decisions_with_bounded_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomy_decisions.jsonl"
            records = [
                {"decision_id": "ok-1", "status": "completed", "action": "market_refresh", "outcome": {"status": "completed"}},
                {"decision_id": "failed-1", "status": "failed", "action": "market_refresh", "authority": "GREEN",
                 "outcome": {"status": "failed", "command": "scripts/universal_market_cycle.py",
                             "returncode": 1, "stderr_tail": "x" * 2500}},
                {"decision_id": "failed-2", "status": "failed", "action": "candidate_recovery", "authority": "GREEN",
                 "outcome": {"status": "failed", "command": "scripts/cash_first_recovery_cycle.py",
                             "returncode": 1, "reason": "schema mismatch"}},
            ]
            path.write_text(
                "not-json\n" + "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            failures = recent_autonomy_failures(path, limit=2)

            self.assertEqual(["failed-1", "failed-2"], [item["decision_id"] for item in failures])
            self.assertEqual("scripts/universal_market_cycle.py", failures[0]["command"])
            self.assertEqual(2000, len(failures[0]["stderr_tail"]))
            self.assertEqual("schema mismatch", failures[1]["reason"])

    def test_missing_file_and_non_positive_limit_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.jsonl"
            self.assertEqual([], recent_autonomy_failures(missing))
            self.assertEqual([], recent_autonomy_failures(missing, limit=0))


if __name__ == "__main__":
    unittest.main()
