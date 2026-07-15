import os
import unittest
from unittest.mock import patch

from atlas.orchestrator import orchestrate_mission
from atlas.providers import ModelResponse


class OrchestratorTests(unittest.TestCase):
    def test_safe_mission_rechecks_revision_before_synthesis(self):
        responses = [
            ModelResponse("test", "fake", "draft answer"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nAdd risks."),
            ModelResponse("test", "fake", "revised answer"),
            ModelResponse("test", "fake", "VERDICT: PASS\nComplete and safe."),
            ModelResponse("test", "fake", "final answer"),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission(
                "research",
                "Analyse supplier risk",
                {"domain": "sourcing"},
                [{
                    "memory_id": "m1",
                    "memory_type": "fact",
                    "domain": "sourcing",
                    "content": "Supplier is new",
                    "confidence": 0.7,
                }],
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.final_answer, "final answer")
        self.assertEqual(result.revision_count, 1)
        self.assertEqual(
            [trace.stage for trace in result.traces],
            ["planning", "specialist", "critique", "revision_1", "critique_2", "synthesis", "output_validation"],
        )
        self.assertEqual(mocked.call_count, 5)

    def test_two_revisions_are_bounded_and_rechecked(self):
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nFirst correction."),
            ModelResponse("test", "fake", "revision one"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nSecond correction."),
            ModelResponse("test", "fake", "revision two"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nStill imperfect."),
            ModelResponse("test", "fake", "final bounded answer"),
        ]
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "2"}, clear=False):
            with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
                result = orchestrate_mission("research", "Analyse supplier risk", {}, [])

        self.assertEqual(result.revision_count, 2)
        self.assertEqual(mocked.call_count, 7)
        self.assertIn("revision_2", [trace.stage for trace in result.traces])

    def test_invalid_revision_configuration_falls_back_safely(self):
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nCorrect it."),
            ModelResponse("test", "fake", "revision"),
            ModelResponse("test", "fake", "VERDICT: PASS\nGood."),
            ModelResponse("test", "fake", "final"),
        ]
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "invalid"}, clear=False):
            with patch("atlas.orchestrator.complete", side_effect=responses):
                result = orchestrate_mission("research", "Compare suppliers", {}, [])
        self.assertEqual(result.revision_count, 1)

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
        self.assertEqual(
            [trace.stage for trace in result.traces],
            ["planning", "specialist", "critique", "synthesis", "output_validation"],
        )
        self.assertEqual(mocked.call_count, 3)

    def test_contract_failure_triggers_repair_and_revalidation(self):
        objective = "Livrables obligatoires : tableau de marge, classement score /10, plan 90 jours semaine par semaine, décision finale Go / No-Go, calcul explicite."
        repaired = """| Scénario | Marge brute | Marge/kg | Taux de marge |
|---|---:|---:|---:|
| 12 t | 1200 EUR | 0,10 EUR | 8% |
| 17 t | 3400 EUR | 0,20 EUR | 15% |

Calcul : coût par kg = coût total / kg.
1. Segment A — score 9/10
2. Segment B — score 8/10
3. Segment C — score 7/10
Semaine 1 : qualifier. Semaine 2 : contacter. Semaine 3 : relancer. Semaine 4 : négocier.
Décision finale : Go sous conditions.
"""
        responses = [
            ModelResponse("test", "fake", "draft vague"),
            ModelResponse("test", "fake", "VERDICT: PASS\nLooks good."),
            ModelResponse("test", "fake", "final vague"),
            ModelResponse("test", "fake", repaired),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses):
            result = orchestrate_mission("research", objective, {}, [])
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.revision_count, 1)
        self.assertIn("contract_repair", [trace.stage for trace in result.traces])
        self.assertIn("output_revalidation", [trace.stage for trace in result.traces])

    def test_unrepaired_contract_is_not_marked_completed(self):
        objective = "Livrables obligatoires : tableau de marge et décision finale Go / No-Go."
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "VERDICT: PASS\nOK"),
            ModelResponse("test", "fake", "vague final"),
            ModelResponse("test", "fake", "still vague"),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses):
            result = orchestrate_mission("research", objective, {}, [])
        self.assertEqual(result.status, "failed_validation")
        self.assertTrue(result.final_answer.startswith("OUTPUT VALIDATION FAILED"))

    def test_trace_output_is_bounded(self):
        long_text = "x" * 5000
        responses = [
            ModelResponse("test", "fake", long_text),
            ModelResponse("test", "fake", "VERDICT: PASS\nSafe."),
            ModelResponse("test", "fake", "final"),
        ]
        with patch.dict(os.environ, {"ORCHESTRATOR_TRACE_MAX_CHARS": "1000"}, clear=False):
            with patch("atlas.orchestrator.complete", side_effect=responses):
                result = orchestrate_mission("research", "Compare suppliers", {}, [])
        specialist_trace = next(trace for trace in result.traces if trace.stage == "specialist")
        self.assertLessEqual(len(specialist_trace.output), 1020)
        self.assertTrue(specialist_trace.output.endswith("[trace truncated]"))


if __name__ == "__main__":
    unittest.main()
