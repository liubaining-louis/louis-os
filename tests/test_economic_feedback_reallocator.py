from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.economic_feedback_reallocator import EconomicFeedbackReallocator, MissionEconomics


class EconomicFeedbackReallocatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reallocator = EconomicFeedbackReallocator(minimum_sample_size=5)

    def mission(self, mission_id: str, **overrides) -> MissionEconomics:
        values = {
            "mission_id": mission_id,
            "sample_size": 10,
            "booked_revenue": 1000.0,
            "booked_gross_profit": 300.0,
            "expected_gross_profit": 500.0,
            "conversion_rate": 0.25,
            "current_budget": 100.0,
            "strategic_fit": 0.8,
        }
        values.update(overrides)
        return MissionEconomics(**values)

    def test_stops_non_positive_economics_after_sufficient_sample(self):
        result = self.reallocator.reallocate([
            self.mission("bad", expected_gross_profit=-10.0, booked_revenue=0.0, booked_gross_profit=0.0)
        ], total_budget=1000.0)
        self.assertEqual(result.allocations[0].decision, "stop")
        self.assertEqual(result.allocations[0].allocated_budget, 0.0)

    def test_accelerates_proven_margin_and_conversion(self):
        result = self.reallocator.reallocate([self.mission("winner")], total_budget=1000.0)
        self.assertEqual(result.allocations[0].decision, "accelerate")
        self.assertGreater(result.allocations[0].allocated_budget, 0.0)

    def test_holds_revenue_with_weak_margin(self):
        result = self.reallocator.reallocate([
            self.mission("thin", booked_revenue=1000.0, booked_gross_profit=50.0)
        ], total_budget=1000.0)
        self.assertEqual(result.allocations[0].decision, "hold")
        self.assertEqual(result.allocations[0].allocated_budget, 0.0)

    def test_preserves_bounded_exploration_for_small_samples(self):
        result = self.reallocator.reallocate([
            self.mission("new", sample_size=2, booked_revenue=0.0, booked_gross_profit=0.0, expected_gross_profit=0.0)
        ], total_budget=1000.0)
        self.assertEqual(result.allocations[0].decision, "continue")
        self.assertGreater(result.allocations[0].allocated_budget, 0.0)

    def test_never_exceeds_maximum_mission_share(self):
        result = self.reallocator.reallocate([self.mission("winner")], total_budget=1000.0)
        self.assertLessEqual(result.allocations[0].allocated_budget, 500.0)

    def test_rejects_duplicate_missions(self):
        with self.assertRaises(ValueError):
            self.reallocator.reallocate([self.mission("same"), self.mission("same")], total_budget=100.0)

    def test_writes_auditable_artifact(self):
        result = self.reallocator.reallocate([self.mission("winner")], total_budget=1000.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reallocation.json"
            self.reallocator.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["economic_reallocation"]["allocations"][0]["mission_id"], "winner")


if __name__ == "__main__":
    unittest.main()
