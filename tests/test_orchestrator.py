import os
import unittest
from unittest.mock import patch

from atlas.orchestrator import orchestrate_mission
from atlas.missions import run_mission
from atlas.providers import ModelResponse


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_exhausted_critic_rejection_is_not_completed(self):
        responses = [ModelResponse("test", "fake", text) for text in (
            "draft", "VERDICT: REVISE\nIncorrect facts.", "revised draft",
            "VERDICT: REVISE\nStill incorrect.", "unreviewed synthesis",
        )]
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "1"}):
            with patch("atlas.orchestrator.complete", side_effect=responses):
                result = orchestrate_mission("research", "Compare suppliers", {}, [])
        self.assertEqual(result.status, "failed_validation")

    def test_safe_mission_returns_the_exact_reviewed_revision(self):
        responses = [
            ModelResponse("test", "fake", "draft answer"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nAdd risks."),
            ModelResponse("test", "fake", "revised answer"),
            ModelResponse("test", "fake", "VERDICT: PASS\nComplete and safe."),
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
        self.assertEqual(result.final_answer, "revised answer")
        self.assertEqual(result.revision_count, 1)
        self.assertEqual(
            [trace.stage for trace in result.traces],
            ["planning", "specialist", "output_validation", "critique", "revision_1", "output_revalidation_1", "critique_2"],
        )
        self.assertEqual(mocked.call_count, 4)
        self.assertIn('"domain": "sourcing"', mocked.call_args_list[2].args[0])
        self.assertIn("Supplier is new", mocked.call_args_list[2].args[0])

    def test_two_revisions_are_bounded_and_rechecked(self):
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nFirst correction."),
            ModelResponse("test", "fake", "revision one"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nSecond correction."),
            ModelResponse("test", "fake", "revision two"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nStill imperfect."),
        ]
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "2"}, clear=False):
            with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
                result = orchestrate_mission("research", "Analyse supplier risk", {}, [])

        self.assertEqual(result.revision_count, 2)
        self.assertEqual(mocked.call_count, 6)
        self.assertEqual(result.status, "failed_validation")
        self.assertIn("revision_2", [trace.stage for trace in result.traces])

    def test_invalid_revision_configuration_falls_back_safely(self):
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "VERDICT: REVISE\nCorrect it."),
            ModelResponse("test", "fake", "revision"),
            ModelResponse("test", "fake", "VERDICT: PASS\nGood."),
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
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission("research", "Compare two suppliers", {}, [])

        self.assertEqual(result.revision_count, 0)
        self.assertEqual(result.final_answer, "draft answer")
        self.assertEqual(
            [trace.stage for trace in result.traces],
            ["planning", "specialist", "output_validation", "critique"],
        )
        self.assertEqual(mocked.call_count, 2)

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
            ModelResponse("test", "fake", repaired),
            ModelResponse("test", "fake", "VERDICT: PASS\nChecked the repaired answer."),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission("research", objective, {}, [])
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.revision_count, 1)
        self.assertEqual(result.final_answer, repaired)
        self.assertEqual(mocked.call_count, 3)
        self.assertIn("revision_1", [trace.stage for trace in result.traces])
        self.assertIn("output_revalidation_1", [trace.stage for trace in result.traces])

    def test_unrepaired_contract_is_not_marked_completed(self):
        objective = "Livrables obligatoires : tableau de marge et décision finale Go / No-Go."
        responses = [
            ModelResponse("test", "fake", "draft"),
            ModelResponse("test", "fake", "still vague"),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission("research", objective, {}, [])
        self.assertEqual(result.status, "failed_validation")
        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(result.final_answer.startswith("OUTPUT VALIDATION FAILED"))

    def test_trace_output_is_bounded(self):
        long_text = "x" * 5000
        responses = [
            ModelResponse("test", "fake", long_text),
            ModelResponse("test", "fake", "VERDICT: PASS\nSafe."),
        ]
        with patch.dict(os.environ, {"ORCHESTRATOR_TRACE_MAX_CHARS": "1000"}, clear=False):
            with patch("atlas.orchestrator.complete", side_effect=responses):
                result = orchestrate_mission("research", "Compare suppliers", {}, [])
        specialist_trace = next(trace for trace in result.traces if trace.stage == "specialist")
        self.assertLessEqual(len(specialist_trace.output), 1020)
        self.assertTrue(specialist_trace.output.endswith("[trace truncated]"))

    def test_empty_or_malformed_review_fails_closed_without_extra_call(self):
        for review in ("", "unable to evaluate", "VERDICT: PASS - perhaps", "VERDICT: REVISE - missing facts"):
            with self.subTest(review=review):
                responses = [ModelResponse("test", "fake", "answer"), ModelResponse("test", "fake", review)]
                with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "0"}):
                    with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
                        result = orchestrate_mission("research", "Compare suppliers", {}, [])
                self.assertEqual(result.status, "failed_validation")
                self.assertEqual(result.revision_count, 0)
                self.assertEqual(mocked.call_count, 2)

    def test_zero_revision_budget_also_blocks_structural_repairs(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_REVISIONS": "0"}):
            with patch("atlas.orchestrator.complete", return_value=ModelResponse("test", "fake", "vague")) as mocked:
                result = orchestrate_mission("research", "Livrables obligatoires : tableau de marge.", {}, [])
        self.assertEqual(result.status, "failed_validation")
        self.assertEqual(result.revision_count, 0)
        self.assertEqual(mocked.call_count, 1)

    def test_structural_repair_still_requires_critic_acceptance(self):
        responses = [ModelResponse("test", "fake", text) for text in (
            "", "repaired answer", "VERDICT: REVISE\nUnsupported facts.",
        )]
        with patch("atlas.orchestrator.complete", side_effect=responses) as mocked:
            result = orchestrate_mission("research", "Compare suppliers", {}, [])
        self.assertEqual(result.status, "failed_validation")
        self.assertEqual(mocked.call_count, 3)

    def test_result_identifies_the_author_not_the_critic(self):
        responses = [
            ModelResponse("author", "writer-model", "accepted answer"),
            ModelResponse("reviewer", "judge-model", "VERDICT: PASS\nChecked."),
        ]
        with patch("atlas.orchestrator.complete", side_effect=responses):
            result = orchestrate_mission("research", "Compare suppliers", {}, [])
        self.assertEqual((result.provider, result.model), ("author", "writer-model"))
        self.assertEqual(result.final_answer, "accepted answer")

    def test_review_transport_failure_is_not_a_completed_result(self):
        with patch("atlas.orchestrator.complete", side_effect=[
            ModelResponse("test", "fake", "answer"), RuntimeError("review unavailable"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "review unavailable"):
                orchestrate_mission("research", "Compare suppliers", {}, [])

    def test_failed_acceptance_is_persisted_as_failure_by_mission_service(self):
        responses = [ModelResponse("test", "fake", text) for text in (
            "draft", "VERDICT: REVISE\nWrong.", "revised", "VERDICT: REVISE\nStill wrong.",
        )]
        with patch("atlas.missions.retrieve_memories", return_value=[]), \
             patch("atlas.missions.record_mission_experience", return_value=None) as experience, \
             patch("atlas.missions.get_mission_store") as store, \
             patch("atlas.orchestrator.complete", side_effect=responses):
            record = run_mission("research", "Compare suppliers", {})
        self.assertEqual(record.status, "failed_validation")
        self.assertEqual(store.return_value.save.call_args.args[1]["status"], "failed_validation")
        self.assertEqual(experience.call_args.kwargs["status"], "failed_validation")


if __name__ == "__main__":
    unittest.main()
