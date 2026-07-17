import tempfile
import unittest
from pathlib import Path

from atlas.strategic_goals import (
    JsonlStrategicGoalStore,
    StrategicGoal,
    conflicting_goals,
    reprioritize,
)


class StrategicGoalTests(unittest.TestCase):
    def goal(self, **overrides):
        data = dict(
            goal_id="reliability",
            title="Improve production reliability",
            owner="louis-os",
            metric="success_rate",
            target=0.99,
            current=0.80,
            horizon="2026-Q4",
            priority=90,
        )
        data.update(overrides)
        return StrategicGoal(**data)

    def test_progress_and_priority_score(self):
        goal = self.goal(target=1.0, current=0.75, priority=80)
        self.assertEqual(goal.progress(), 0.75)
        self.assertEqual(goal.priority_score(), 20.0)

    def test_minimize_goal_completes_at_target(self):
        goal = self.goal(metric="cost", target=10, current=8, direction="minimize")
        self.assertEqual(goal.progress(), 1.0)

    def test_store_persists_and_restores_latest_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlStrategicGoalStore(Path(directory) / "goals.jsonl")
            store.save(self.goal())
            updated = store.update_progress("reliability", 0.99)
            self.assertEqual(updated.status, "completed")
            restored = JsonlStrategicGoalStore(store.path).get("reliability")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.current, 0.99)
            self.assertEqual(restored.status, "completed")

    def test_identical_save_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlStrategicGoalStore(Path(directory) / "goals.jsonl")
            first = store.save(self.goal())
            second = store.save(self.goal())
            self.assertEqual(first, second)
            self.assertEqual(len(store.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_abandonment_requires_and_retains_audit_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlStrategicGoalStore(Path(directory) / "goals.jsonl")
            store.save(self.goal())
            with self.assertRaises(ValueError):
                store.abandon("reliability", " ")
            abandoned = store.abandon("reliability", "Metric no longer reflects user value")
            self.assertEqual(abandoned.status, "abandoned")
            self.assertIn("user value", abandoned.abandoned_hypothesis)

    def test_reprioritize_prefers_high_priority_low_progress(self):
        goals = [
            self.goal(goal_id="almost-done", current=0.98, priority=100),
            self.goal(goal_id="large-gap", current=0.50, priority=80),
        ]
        self.assertEqual(reprioritize(goals)[0].goal_id, "large-gap")

    def test_conflicts_are_detected_deterministically(self):
        goals = [
            self.goal(goal_id="raise", metric="latency", direction="maximize"),
            self.goal(goal_id="lower", metric="latency", direction="minimize"),
            self.goal(goal_id="other", metric="cost", direction="minimize"),
        ]
        self.assertEqual(conflicting_goals(goals), [("lower", "raise")])

    def test_invalid_goal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.goal(priority=101).validate()
        with self.assertRaises(ValueError):
            self.goal(status="abandoned").validate()


if __name__ == "__main__":
    unittest.main()
