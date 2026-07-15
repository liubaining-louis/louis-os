import unittest
from unittest.mock import patch

from atlas.orchestrator import orchestrate_mission
from atlas.providers import ModelResponse


class OrchestratorTests(unittest.TestCase):
    def test_safe_mission_runs_specialist_critic_revision_and_synthesis(self):
        responses = [
            ModelResponse("test", "fake", "draft answer"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nAdd risks and missing information."),
            ModelResponse("test", "fake", "revised answer"),
            ModelResponse("test", "fake", "final answer"),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission(
                "research",
                "Analyse supplier risk",
                {"domain": "sourcing"},
                [{"memory_id": "m1", "memory_type": "fact", "domain": "sourcing", "content": "Supplier is new", "confidence": 0.7}],
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.final_answer, "final answer")
        self.assertEqual(result.revision_count, 1)
        self.assertEqual([trace.stage for trace in result.traces], ["planning", "specialist", "critique", "revision", "synthesis"])
        self.assertEqual(mocked.call_count, 4)

    def test_high_risk_external_action_requires_approval_without_llm_call(self):
        with patch("atlas.orchestrator.complete") as mocked:
            result = orchestrate_mission(
                "transaction",
                "Deploy the application to production",
                {},
                [],
            )

        self.assertEqual(result.status, "approval_required")
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.risk_level, "high")
        mocked.assert_not_called()

    def test_passing_critique_skips_revision(self):
        responses = [
            ModelResponse("test", "fake", "draft answer"),
            ModelResponse("test", "fake", "VERDICT: PASS\nComplete and safe."),
            ModelResponse("test", "fake", "final answer"),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission("research", "Compare two suppliers", {}, [])

        self.assertEqual(result.revision_count, 0)
        self.assertEqual([trace.stage for trace in result.traces], ["planning", "specialist", "critique", "synthesis"])
        self.assertEqual(mocked.call_count, 3)


if __name__ == "__main__":
    unittest.main()
