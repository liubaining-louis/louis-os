from __future__ import annotations

import unittest

from atlas.evolution_engine import build_cycle
from atlas.improvement_planner import plan
from atlas.self_diagnostic import diagnose


class EvolutionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "verified_capabilities": ["historique et mémoire permanente Firestore"],
            "autonomous_worker": {
                "verified": True,
                "actions_submitted": 0,
                "opportunities_qualified": 10,
            },
            "monetization": {
                "recorded_evidence_items": 0,
                "recorded_experiments": 0,
                "revenue_received_eur": 0,
            },
        }

    def test_diagnostic_is_deterministic(self) -> None:
        first = diagnose(self.state)
        second = diagnose(self.state)
        self.assertEqual(first, second)
        self.assertEqual(first["method"], "deterministic-runtime-evidence-v1")
        self.assertEqual(len(first["weaknesses"]), 3)

    def test_planner_prioritizes_a_real_gap(self) -> None:
        proposals = plan(diagnose(self.state))
        self.assertTrue(proposals)
        self.assertIn(proposals[0]["capability"], {"monetization", "evidence_discipline", "autonomous_execution"})
        self.assertTrue(proposals[0]["acceptance_criteria"])

    def test_cycle_is_guarded_and_reproducibly_identified(self) -> None:
        first = build_cycle(self.state)
        second = build_cycle(self.state)
        self.assertEqual(
            first["selected_improvement"]["proposal_id"],
            second["selected_improvement"]["proposal_id"],
        )
        self.assertTrue(first["guardrails"]["tests_required"])
        self.assertTrue(first["guardrails"]["benchmark_required"])
        self.assertFalse(first["selected_improvement"]["automatic_production_deploy"])


if __name__ == "__main__":
    unittest.main()
