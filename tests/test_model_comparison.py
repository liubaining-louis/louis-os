from __future__ import annotations

import json
import unittest

from atlas.model_comparison import ComparisonMission, compare_models
from atlas.providers import ModelResponse


class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.mission = ComparisonMission(
            mission_id="coal-email-001",
            objective="Analyser les emails liés au charbon et dégager les grands axes",
            context={"messages": ["Prospect asks for price, MOQ and certification."]},
            providers=["groq", "vertex"],
            evaluation_axes={
                "commercial": ["prix", "price", "moq"],
                "technical": ["certification", "fiche technique"],
            },
        )

    def test_same_prompt_is_sent_to_each_provider(self):
        calls = []

        def invoke(provider, prompt):
            calls.append((provider, prompt))
            return ModelResponse(provider, provider + "-model", "Prix, MOQ et certification.")

        result = compare_models(self.mission, invoke=invoke)
        self.assertEqual(result.status, "completed")
        self.assertEqual([item[0] for item in calls], ["groq", "vertex"])
        self.assertEqual(calls[0][1], calls[1][1])

    def test_provider_provenance_and_outputs_are_separate(self):
        def invoke(provider, _prompt):
            return ModelResponse(provider, provider + "-model", provider + " output")

        result = compare_models(self.mission, invoke=invoke)
        self.assertEqual(result.runs[0].model, "groq-model")
        self.assertEqual(result.runs[1].output, "vertex output")

    def test_partial_provider_failure_blocks_comparison(self):
        def invoke(provider, _prompt):
            if provider == "vertex":
                raise RuntimeError("vertex is not configured")
            return ModelResponse(provider, "model", "prix et certification")

        result = compare_models(self.mission, invoke=invoke)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.runs[1].status, "blocked")
        self.assertFalse(result.best_coverage_provider == "vertex")

    def test_deterministic_coverage_and_discrepancies(self):
        def invoke(provider, _prompt):
            text = "Prix et MOQ." if provider == "groq" else "Certification et fiche technique."
            return ModelResponse(provider, "model", text)

        result = compare_models(self.mission, invoke=invoke)
        self.assertEqual(len(result.discrepancies), 2)
        self.assertEqual(result.runs[0].coverage_score, 0.5)
        self.assertEqual(result.runs[1].coverage_score, 0.5)
        self.assertIsNone(result.best_coverage_provider)

    def test_result_is_json_serializable(self):
        result = compare_models(
            self.mission,
            invoke=lambda provider, _prompt: ModelResponse(provider, "model", "prix et certification"),
        )
        json.dumps(result.to_dict())

    def test_requires_two_distinct_providers(self):
        mission = ComparisonMission("m", "objective", {}, ["groq", "groq"])
        with self.assertRaisesRegex(ValueError, "two distinct"):
            compare_models(mission, invoke=lambda *_args: ModelResponse("groq", "model", "ok"))


if __name__ == "__main__":
    unittest.main()
