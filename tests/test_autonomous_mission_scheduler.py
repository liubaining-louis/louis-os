from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from atlas.autonomous_mission_scheduler import AutonomousMissionScheduler, MissionCandidate


class AutonomousMissionSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = AutonomousMissionScheduler(
            maximum_concurrent_missions=2,
            cooldown_seconds=3600,
            maximum_no_progress_cycles=3,
        )
        self.now = datetime(2026, 7, 18, 18, 0, tzinfo=timezone.utc)

    def candidate(self, mission_id: str, **overrides) -> MissionCandidate:
        values = {
            "mission_id": mission_id,
            "priority_score": 0.7,
            "allocated_budget": 20.0,
            "expected_gross_profit": 100.0,
            "economic_decision": "continue",
        }
        values.update(overrides)
        return MissionCandidate(**values)

    def test_accelerate_mission_is_ranked_first(self):
        result = self.scheduler.schedule(
            [
                self.candidate("normal", expected_gross_profit=500),
                self.candidate("accelerate", economic_decision="accelerate", expected_gross_profit=200),
            ],
            total_budget=100,
            now=self.now,
        )
        self.assertEqual(result.items[0].mission_id, "accelerate")
        self.assertEqual(result.items[0].decision, "launch")

    def test_respects_concurrency_limit(self):
        result = self.scheduler.schedule(
            [self.candidate("active", active=True), self.candidate("a"), self.candidate("b")],
            total_budget=100,
            now=self.now,
        )
        self.assertEqual(result.launch_count, 1)
        self.assertEqual(sum(item.decision == "defer" for item in result.items), 2)

    def test_stops_economically_stopped_and_stagnant_missions(self):
        result = self.scheduler.schedule(
            [
                self.candidate("economic-stop", economic_decision="stop"),
                self.candidate("stagnant", consecutive_no_progress_cycles=3),
            ],
            total_budget=100,
            now=self.now,
        )
        self.assertTrue(all(item.decision == "stop" for item in result.items))

    def test_enforces_cooldown(self):
        result = self.scheduler.schedule(
            [self.candidate("recent", last_started_at="2026-07-18T17:30:00Z")],
            total_budget=100,
            now=self.now,
        )
        self.assertEqual(result.items[0].decision, "cooldown")

    def test_blocks_when_budget_is_insufficient(self):
        result = self.scheduler.schedule(
            [self.candidate("expensive", allocated_budget=80)],
            total_budget=50,
            now=self.now,
        )
        self.assertEqual(result.items[0].decision, "blocked")
        self.assertEqual(result.reserved_budget, 0)

    def test_budget_and_order_are_deterministic(self):
        candidates = [
            self.candidate("b", allocated_budget=25, expected_gross_profit=100),
            self.candidate("a", allocated_budget=25, expected_gross_profit=100),
        ]
        first = self.scheduler.schedule(candidates, total_budget=50, now=self.now)
        second = self.scheduler.schedule(reversed(candidates), total_budget=50, now=self.now)
        self.assertEqual(first, second)
        self.assertEqual(first.reserved_budget, 50)

    def test_rejects_duplicate_missions(self):
        with self.assertRaises(ValueError):
            self.scheduler.schedule(
                [self.candidate("same"), self.candidate("same")],
                total_budget=100,
                now=self.now,
            )

    def test_writes_auditable_artifact(self):
        result = self.scheduler.schedule([self.candidate("m1")], total_budget=50, now=self.now)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            self.scheduler.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["mission_schedule"]["launch_count"], 1)


if __name__ == "__main__":
    unittest.main()
