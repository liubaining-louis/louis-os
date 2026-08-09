from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.autonomy_kernel import build_state, choose_next_action, update_learning


class AutonomyKernelTests(unittest.TestCase):
    def test_sparse_market_selects_market_refresh(self) -> None:
        state = {
            "cycle": 1,
            "opportunities_observed": 0,
            "candidates": 0,
            "executable_now": 0,
            "prepare_then_gate": 0,
            "multi_model_recommendation": None,
            "last_autonomous_action": None,
            "last_autonomous_action_effect": 0,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "market_refresh")
        self.assertEqual(decision.authority, "GREEN")

    def test_executable_candidate_takes_priority(self) -> None:
        state = {
            "cycle": 2,
            "opportunities_observed": 10,
            "candidates": 2,
            "executable_now": 1,
            "prepare_then_gate": 0,
            "multi_model_recommendation": "execute_now",
            "last_autonomous_action": "market_refresh",
            "last_autonomous_action_effect": 1,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "execution_attempt")

    def test_ineffective_repetition_is_demoted(self) -> None:
        state = {
            "cycle": 3,
            "opportunities_observed": 0,
            "candidates": 0,
            "executable_now": 0,
            "prepare_then_gate": 0,
            "multi_model_recommendation": None,
            "last_autonomous_action": "market_refresh",
            "last_autonomous_action_effect": 0,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "candidate_recovery")

    def test_due_factory_plan_selects_market_refresh_over_recovery(self) -> None:
        state = {
            "cycle": 500,
            "opportunities_observed": 12,
            "candidates": 0,
            "executable_now": 0,
            "prepare_then_gate": 0,
            "multi_model_recommendation": None,
            "market_next_action": "execute_opportunity_factory_query_pack",
            "market_refresh_age_cycles": 150,
            "last_autonomous_action": "candidate_recovery",
            "last_autonomous_action_effect": 0,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "market_refresh")
        self.assertIn("cash-first source expansion", decision.hypothesis)

    def test_periodic_refresh_runs_without_expansion_hint_after_cooldown(self) -> None:
        state = {
            "cycle": 500,
            "opportunities_observed": 12,
            "candidates": 1,
            "executable_now": 0,
            "prepare_then_gate": 0,
            "multi_model_recommendation": None,
            "market_next_action": "prepare_simple_mission_proposal_dossiers",
            "market_refresh_age_cycles": 12,
            "last_autonomous_action": "quality_review",
            "last_autonomous_action_effect": 0,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "market_refresh")
        self.assertIn("hourly internet-market freshness", decision.hypothesis)

    def test_factory_refresh_respects_bounded_cooldown(self) -> None:
        state = {
            "cycle": 500,
            "opportunities_observed": 12,
            "candidates": 0,
            "executable_now": 0,
            "prepare_then_gate": 0,
            "multi_model_recommendation": None,
            "market_next_action": "execute_opportunity_factory_query_pack",
            "market_refresh_age_cycles": 10,
            "last_autonomous_action": "quality_review",
            "last_autonomous_action_effect": 0,
        }
        decision = choose_next_action(state)
        self.assertEqual(decision.action, "candidate_recovery")

    def test_state_and_learning_are_persistent_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "universal_market_cycle.json").write_text(json.dumps({"opportunities_observed": 3, "opportunities_executable_now": 0}))
            (results / "monetization_candidates.json").write_text(json.dumps({"candidates": [{"id": "a"}]}))
            (results / "autonomy_state.json").write_text(json.dumps({"cycle": 200}))
            (results / "autonomy_learning.json").write_text(json.dumps({
                "actions": {
                    "market_refresh": {
                        "last_decision_id": "autonomy-00000100-market_refresh",
                    }
                }
            }))
            state = build_state(results)
            self.assertEqual(state["opportunities_observed"], 3)
            self.assertEqual(state["candidates"], 1)
            self.assertEqual(state["last_market_refresh_cycle"], 100)
            self.assertEqual(state["market_refresh_age_cycles"], 101)
            self.assertEqual(state["market_refresh_cooldown_cycles"], 12)
            decision = choose_next_action(state)
            learning = update_learning(results, decision, {"status": "completed", "measured_delta": {"candidates": 1}})
            self.assertEqual(learning["actions"][decision.action]["attempts"], 1)
            self.assertEqual(learning["actions"][decision.action]["effective"], 1)
            self.assertTrue((results / "autonomy_learning.json").exists())


if __name__ == "__main__":
    unittest.main()
