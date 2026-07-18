from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.experiment_outcomes import ExperimentEvaluation
from atlas.venture_next_actions import VentureNextActionPlanner


class VentureNextActionPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = VentureNextActionPlanner()

    def evaluation(self, decision: str, experiment_id: str = "exp-1") -> ExperimentEvaluation:
        return ExperimentEvaluation(
            experiment_id=experiment_id,
            decision=decision,  # type: ignore[arg-type]
            observed_rate=0.3,
            threshold=0.25,
            reasons=("test reason",),
        )

    def test_continue_prepares_scale_without_external_execution(self) -> None:
        action = self.planner.plan(self.evaluation("continue"))
        self.assertEqual(action.action_kind, "prepare_scale")
        self.assertEqual(action.priority, 1)
        self.assertFalse(action.external_execution_allowed)
        self.assertTrue(any("dry-run" in task for task in action.tasks))

    def test_revise_changes_one_material_assumption(self) -> None:
        action = self.planner.plan(self.evaluation("revise"))
        self.assertEqual(action.action_kind, "revise_experiment")
        self.assertEqual(action.priority, 2)
        self.assertTrue(any("exactly one" in task for task in action.tasks))

    def test_stop_archives_and_blocks_automatic_reactivation(self) -> None:
        action = self.planner.plan(self.evaluation("stop"))
        self.assertEqual(action.action_kind, "archive_venture")
        self.assertEqual(action.priority, 3)
        self.assertTrue(any("ineligible" in task for task in action.tasks))

    def test_plan_many_is_priority_then_id_sorted(self) -> None:
        actions = self.planner.plan_many([
            self.evaluation("stop", "exp-b"),
            self.evaluation("continue", "exp-c"),
            self.evaluation("continue", "exp-a"),
        ])
        self.assertEqual([item.experiment_id for item in actions], ["exp-a", "exp-c", "exp-b"])

    def test_writes_versioned_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "actions.json"
            result = self.planner.write([self.planner.plan(self.evaluation("continue"))], path)
            payload = json.loads(Path(result).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["action_count"], 1)
        self.assertFalse(payload["actions"][0]["external_execution_allowed"])

    def test_rejects_unknown_decision(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.planner.plan(self.evaluation("unknown"))


if __name__ == "__main__":
    unittest.main()
