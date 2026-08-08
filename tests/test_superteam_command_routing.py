from __future__ import annotations

import unittest
from unittest.mock import patch

from atlas.commands import _is_market_access_closed_loop, _is_superteam_crypto_closed_loop, create_command


ISSUE_270_ORDER = (
    "Owner authorization: execute the Superteam crypto-bounty closed loop now using the "
    "deterministic_superteam_executor after successful VM-local credential bootstrap. "
    "Discover current AGENT_ALLOWED / AGENT_ONLY listings through the official agent API. "
    "Prefer execute_now. If a complete compliant submission package exists for the selected "
    "listing, submit it directly without an AI approval gate and require an external receipt."
)

MARKET_ACCESS_ORDER = (
    "Owner authorization: execute now. Build the internet-wide market access layer across multiple sources. "
    "Use Superteam as one seed source, then continue to other marketplaces and the source registry until a "
    "legitimate quick-win mission enters BUILDING and can be submitted."
)


class SuperteamCommandRoutingTests(unittest.TestCase):
    def test_issue_270_text_forces_superteam_route(self) -> None:
        self.assertTrue(_is_superteam_crypto_closed_loop(ISSUE_270_ORDER))

    def test_market_access_intent_is_recognized_even_when_superteam_is_mentioned(self) -> None:
        self.assertTrue(_is_market_access_closed_loop(MARKET_ACCESS_ORDER))
        self.assertTrue(_is_superteam_crypto_closed_loop(MARKET_ACCESS_ORDER))

    @patch("atlas.commands._save")
    @patch("atlas.commands._find_by_idempotency_key", return_value=None)
    @patch("atlas.commands.validate_plan", return_value=(True, []))
    @patch("atlas.commands.build_plan")
    @patch("atlas.commands.delegate_superteam_to_vm")
    def test_issue_270_delegates_to_vm_and_never_falls_through_to_generative_mission(
        self, delegate, build_plan, _validate_plan, _find, _save
    ) -> None:
        class Plan:
            requires_external_action = True
            mission_type = "generic"
            def to_dict(self):
                return {"mission_type": self.mission_type, "requires_external_action": True}

        build_plan.return_value = Plan()
        delegate.return_value = {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "prepare_then_gate",
            "evidence": ["firestore:louis_vm_commands/test"],
        }
        with patch("atlas.commands.run_mission") as run_mission:
            result = create_command(ISSUE_270_ORDER, idempotency_key="issue-270-regression")
        self.assertEqual(result["execution_mode"], "deterministic_superteam_executor")
        delegate.assert_called_once()
        self.assertEqual(delegate.call_args.kwargs["order"], ISSUE_270_ORDER)
        run_mission.assert_not_called()

    @patch("atlas.commands._save")
    @patch("atlas.commands._find_by_idempotency_key", return_value=None)
    @patch("atlas.commands.validate_plan", return_value=(True, []))
    @patch("atlas.commands.build_plan")
    def test_market_access_route_has_precedence_over_superteam_only_executor(
        self, build_plan, _validate_plan, _find, _save
    ) -> None:
        class Plan:
            requires_external_action = True
            mission_type = "generic"
            def to_dict(self):
                return {"mission_type": self.mission_type, "requires_external_action": True}

        build_plan.return_value = Plan()
        broad_outcome = {
            "status": "blocked",
            "reason": "no_authentic_executable_candidate",
            "evidence": ["results/monetization_execution_diagnosis.json"],
            "diagnosis": {"blocked_stage": "opportunity_discovery", "next_action": "expand_verified_provider_sources_and_refresh"},
        }
        with (
            patch("atlas.commands.run_self_healing_deliverable_cycle", return_value=broad_outcome) as broad,
            patch("atlas.commands.delegate_superteam_to_vm") as superteam,
            patch("atlas.commands.run_mission") as run_mission,
        ):
            result = create_command(MARKET_ACCESS_ORDER, idempotency_key="market-access-routing-regression")

        self.assertEqual(result["execution_mode"], "deterministic_market_access_executor")
        broad.assert_called_once()
        superteam.assert_not_called()
        run_mission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
