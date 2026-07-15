import unittest

from atlas.core import MissionPlan, build_plan, classify_mission, validate_plan


class MissionCoreTests(unittest.TestCase):
    def test_classifies_research_mission(self) -> None:
        self.assertEqual(
            classify_mission("Compare three supplier offers"),
            ("research", "research_workflow", "low"),
        )

    def test_high_risk_mission_requires_approval(self) -> None:
        plan = build_plan("Deploy the new version to production")
        self.assertEqual(plan.mission_type, "transaction")
        self.assertEqual(plan.risk_level, "high")
        self.assertTrue(plan.requires_external_action)
        self.assertIn("request_human_approval", plan.steps)
        self.assertEqual(validate_plan(plan), (True, []))

    def test_empty_objective_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_plan("   ")

    def test_invalid_high_risk_plan_is_detected(self) -> None:
        plan = MissionPlan(
            mission_type="transaction",
            workflow="approval_workflow",
            risk_level="high",
            requires_external_action=True,
            steps=["validate_input", "execute_workflow", "evaluate_output"],
        )
        valid, errors = validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("high-risk plan requires human approval", errors)

    def test_plan_is_json_ready(self) -> None:
        plan = build_plan("Write an email to a supplier", {"language": "en"})
        payload = plan.to_dict()
        self.assertEqual(payload["workflow"], "communication_workflow")
        self.assertIsInstance(payload["steps"], list)


if __name__ == "__main__":
    unittest.main()
