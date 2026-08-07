from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from atlas.adaptive_model_router import assess_difficulty, routed_complete
from atlas.providers import ModelResponse


class AdaptiveModelRouterTests(unittest.TestCase):
    def test_simple_status_question_stays_fast(self) -> None:
        decision = assess_difficulty("Quel est ton statut maintenant ?")
        self.assertEqual(decision.tier, "fast")
        self.assertLess(decision.score, 0.55)

    def test_external_monetization_decision_escalates(self) -> None:
        prompt = (
            "Analyse la cause racine de ce blocage execute_now et vérifie si une soumission "
            "externe avec paiement peut être exécutée sans risque ni régression."
        )
        decision = assess_difficulty(prompt)
        self.assertEqual(decision.tier, "reasoning")
        self.assertGreaterEqual(decision.score, 0.55)
        self.assertIn("economic_or_external_boundary", decision.reasons)

    @patch("atlas.adaptive_model_router.complete_with")
    def test_reasoning_tier_targets_vertex(self, complete_with) -> None:
        complete_with.return_value = ModelResponse("vertex", "gemini-test", "reasoned")
        result = routed_complete(
            "Diagnose la cause racine, compare les risques et vérifie la soumission et le paiement."
        )
        complete_with.assert_called_once()
        self.assertEqual(complete_with.call_args.args[0], "vertex")
        self.assertTrue(result.escalated)
        self.assertFalse(result.escalation_fallback)

    @patch("atlas.adaptive_model_router.complete")
    @patch("atlas.adaptive_model_router.complete_with")
    def test_reasoning_failure_falls_back_safely(self, complete_with, complete) -> None:
        complete_with.side_effect = RuntimeError("vertex unavailable")
        complete.return_value = ModelResponse("groq", "llama-test", "fallback")
        result = routed_complete(
            "Diagnose la cause racine, compare les risques et vérifie la soumission et le paiement."
        )
        self.assertEqual(result.provider, "groq")
        self.assertTrue(result.escalated)
        self.assertTrue(result.escalation_fallback)

    def test_threshold_is_configurable_but_bounded(self) -> None:
        with patch.dict(os.environ, {"LLM_REASONING_ESCALATION_THRESHOLD": "0.2"}):
            decision = assess_difficulty("Compare cette architecture")
        self.assertEqual(decision.tier, "reasoning")


if __name__ == "__main__":
    unittest.main()
