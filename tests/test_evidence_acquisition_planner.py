from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.evidence_acquisition_planner import EvidenceAcquisitionPlanner, EvidenceGap


class EvidenceAcquisitionPlannerTests(unittest.TestCase):
    def test_prioritizes_high_value_gap(self) -> None:
        planner = EvidenceAcquisitionPlanner(maximum_tasks=2)
        tasks = planner.plan("m1", "Find a viable B2B offer", [
            EvidenceGap("pricing", 0.4, 0.5, 0.5),
            EvidenceGap("demand", 0.9, 0.8, 0.9),
            EvidenceGap("risk", 0.2, 0.2, 0.2),
        ])
        self.assertEqual(tasks[0].evidence_type, "demand")
        self.assertEqual(len(tasks), 2)

    def test_respects_cost_and_source_bounds(self) -> None:
        planner = EvidenceAcquisitionPlanner(maximum_sources_per_task=3, total_cost_score=0.12)
        tasks = planner.plan("m1", "Assess opportunity", [
            EvidenceGap("demand", 0.8, 0.8, 0.8),
            EvidenceGap("pricing", 0.7, 0.7, 0.7),
        ])
        self.assertTrue(all(task.maximum_sources == 3 for task in tasks))
        self.assertLessEqual(sum(task.maximum_cost_score for task in tasks), 0.120001)

    def test_assigns_method_by_evidence_type(self) -> None:
        planner = EvidenceAcquisitionPlanner()
        tasks = planner.plan("m1", "Assess opportunity", [EvidenceGap("risk", 1.0, 1.0, 1.0)])
        self.assertEqual(tasks[0].method, "official_registry")
        self.assertIn("two independent", tasks[0].stop_condition)

    def test_is_deterministic(self) -> None:
        gaps = [
            EvidenceGap("pricing", 0.5, 0.5, 0.5),
            EvidenceGap("competition", 0.5, 0.5, 0.5),
        ]
        planner = EvidenceAcquisitionPlanner()
        first = planner.plan("m1", "Assess opportunity", gaps)
        second = planner.plan("m1", "Assess opportunity", reversed(gaps))
        self.assertEqual(first, second)

    def test_writes_versioned_artifact(self) -> None:
        planner = EvidenceAcquisitionPlanner()
        tasks = planner.plan("m1", "Assess opportunity", [EvidenceGap("demand", 0.8, 0.8, 0.8)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research_plan.json"
            planner.write(tasks, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["task_count"], 1)


if __name__ == "__main__":
    unittest.main()
