import tempfile
import unittest
from pathlib import Path

from atlas.autonomous import (
    ActionBudget,
    JsonlCycleStore,
    Opportunity,
    run_cycle,
    score_opportunity,
)


class AutonomousLoopTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = JsonlCycleStore(Path(self.tempdir.name) / "cycles.jsonl")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_scoring_is_deterministic_and_bounded(self):
        opportunity = Opportunity("a", "Improve test coverage", 0.9, 0.7, 0.8, 0.2, 0.1)
        self.assertEqual(score_opportunity(opportunity), score_opportunity(opportunity))
        self.assertGreaterEqual(score_opportunity(opportunity), 0.0)
        self.assertLessEqual(score_opportunity(opportunity), 1.0)

    def test_dry_run_completes_all_stages_without_promotion(self):
        opportunity = Opportunity("a", "Improve test coverage", 0.9, 0.7, 0.8, 0.2, 0.1)
        record = run_cycle("obs-1", [opportunity], self.store)
        self.assertEqual(record.status, "simulated")
        self.assertEqual(
            record.stages,
            ["observe", "prioritize", "plan", "simulate", "evaluate", "learn"],
        )
        self.assertFalse(record.promoted)

    def test_duplicate_cycle_is_idempotent(self):
        opportunity = Opportunity("a", "Improve test coverage", 0.9, 0.7, 0.8, 0.2, 0.1)
        first = run_cycle("obs-1", [opportunity], self.store)
        second = run_cycle("obs-1", [opportunity], self.store)
        self.assertEqual(first.cycle_id, second.cycle_id)
        lines = (Path(self.tempdir.name) / "cycles.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)

    def test_unsafe_action_requires_approval(self):
        opportunity = Opportunity(
            "a", "Rotate production secret", 1.0, 1.0, 0.9, 0.1, 0.1, "secret_change"
        )
        record = run_cycle("obs-unsafe", [opportunity], self.store)
        self.assertEqual(record.status, "approval_required")
        self.assertEqual(record.reason, "unsafe_action_requires_explicit_approval")

    def test_budget_and_confidence_stop_cycle(self):
        opportunity = Opportunity("a", "Uncertain change", 1.0, 1.0, 0.4, 0.1, 0.1)
        record = run_cycle(
            "obs-budget",
            [opportunity],
            self.store,
            budget=ActionBudget(max_actions=1, max_risk=0.25, min_confidence=0.65),
        )
        self.assertEqual(record.status, "stopped")

    def test_regression_blocks_promotion(self):
        opportunity = Opportunity("a", "Safe code change", 0.9, 0.7, 0.8, 0.2, 0.1)
        record = run_cycle(
            "obs-regression",
            [opportunity],
            self.store,
            dry_run=False,
            regression_detected=True,
        )
        self.assertEqual(record.status, "blocked")
        self.assertFalse(record.promoted)
        self.assertEqual(record.reason, "regression_detected")


if __name__ == "__main__":
    unittest.main()
