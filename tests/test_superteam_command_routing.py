from __future__ import annotations

import unittest
from unittest.mock import patch

from atlas.commands import _is_superteam_crypto_closed_loop, create_command


ISSUE_270_ORDER = (
    "Owner authorization: execute the Superteam crypto-bounty closed loop now using the "
    "deterministic_superteam_executor after successful VM-local credential bootstrap. "
    "Discover current AGENT_ALLOWED / AGENT_ONLY listings through the official agent API. "
    "Prefer execute_now. If a complete compliant submission package exists for the selected "
    "listing, submit it directly without an AI approval gate and require an external receipt."
)


class SuperteamCommandRoutingTests(unittest.TestCase):
    def test_issue_270_text_forces_superteam_route(self) -> None:
        self.assertTrue(_is_superteam_crypto_closed_loop(ISSUE_270_ORDER))

    @patch("atlas.commands._save")
    @patch("atlas.commands._find_by_idempotency_key", return_value=None)
    @patch("atlas.commands.validate_plan", return_value=(True, []))
    @patch("atlas.commands.build_plan")
    @patch("atlas.commands.run_superteam_crypto_cycle")
    def test_issue_270_never_falls_through_to_generative_mission(
        self, run_superteam, build_plan, _validate_plan, _find, _save
    ) -> None:
        class Plan:
            requires_external_action = True
            mission_type = "generic"
            def to_dict(self):
                return {"mission_type": self.mission_type, "requires_external_action": True}

        build_plan.return_value = Plan()
        run_superteam.return_value = {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "prepare_then_gate",
            "evidence": ["results/superteam_candidates.json"],
        }
        with patch("atlas.commands.run_mission") as run_mission:
            result = create_command(ISSUE_270_ORDER, idempotency_key="issue-270-regression")
        self.assertEqual(result["execution_mode"], "deterministic_superteam_executor")
        run_superteam.assert_called_once()
        run_mission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
