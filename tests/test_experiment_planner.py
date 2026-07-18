from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.experiment_planner import OpportunityExperimentPlanner
from atlas.venture_runtime import Opportunity


def opportunity(**overrides):
    values = {
        "opportunity_id": "opp-abc123",
        "title": "Automated distributor qualification",
        "problem": "Suppliers waste time on poorly qualified leads",
        "target_customer": "B2B charcoal exporters",
        "proposed_offer": "an automated distributor qualification report",
        "evidence_references": ["https://example.com/evidence"],
        "expected_value": 0.8,
        "autonomy": 0.9,
        "learning_value": 0.7,
        "speed": 0.8,
        "human_dependency": 0.1,
        "cost": 0.2,
        "risk": 0.2,
    }
    values.update(overrides)
    return Opportunity(**values)


class OpportunityExperimentPlannerTests(unittest.TestCase):
    def test_builds_bounded_measurable_plan(self) -> None:
        plan = OpportunityExperimentPlanner().plan(opportunity())

        self.assertEqual(plan.experiment_id, "exp-abc123")
        self.assertEqual(plan.primary_metric, "qualified_positive_intent_rate")
        self.assertGreaterEqual(plan.success_threshold, 0.20)
        self.assertEqual(plan.status, "planned")
        self.assertIn("dry-run", " ".join(plan.method))
        self.assertEqual(plan.evidence_references, ("https://example.com/evidence",))

    def test_rejects_experiment_above_cost_gate(self) -> None:
        planner = OpportunityExperimentPlanner(maximum_cost_score=0.35)

        with self.assertRaisesRegex(ValueError, "budget gate"):
            planner.plan(opportunity(cost=0.36))

    def test_rejects_experiment_above_human_dependency_gate(self) -> None:
        planner = OpportunityExperimentPlanner(maximum_human_dependency=0.30)

        with self.assertRaisesRegex(ValueError, "human dependency"):
            planner.plan(opportunity(human_dependency=0.31))

    def test_writes_versioned_artifact(self) -> None:
        planner = OpportunityExperimentPlanner()
        plan = planner.plan(opportunity())
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "experiments.json"
            written = planner.write([plan], output)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(written, str(output))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["experiment_count"], 1)
        self.assertEqual(payload["experiments"][0]["opportunity_id"], "opp-abc123")


if __name__ == "__main__":
    unittest.main()
