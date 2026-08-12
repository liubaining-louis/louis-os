from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.cash_first_usdc_cycle import run_cash_first_usdc_cycle


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def candidate(candidate_id: str, amount: float, *, verified: bool = True) -> dict:
    return {
        "id": candidate_id,
        "title": "Small paid Python fix",
        "url": f"https://example.test/{candidate_id}",
        "reward_hint": amount,
        "currency": "USDC",
        "authenticity_verified": verified,
        "authenticity_status": "verified" if verified else "unverified_reward_claim",
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
        "requires_user_validation": False,
    }


class CashFirstUsdcCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidates_path = self.root / "results" / "monetization_candidates.json"

    def test_only_verified_5_50_usdc_candidates_reach_executor(self) -> None:
        payload = {
            "schema_version": 3,
            "candidates": [
                candidate("too-small", 2),
                candidate("eligible", 12),
                candidate("too-large", 51),
                candidate("unverified", 20, verified=False),
            ],
        }
        write_json(self.candidates_path, payload)
        artifact = self.root / "specific-solution.md"
        artifact.write_text("# BloomFilter implementation\n\nAll acceptance tests passed.\n", encoding="utf-8")
        observed_candidates: list[dict] = []

        def execute(root: Path) -> dict:
            self.assertEqual(root, self.root)
            filtered = json.loads(self.candidates_path.read_text(encoding="utf-8"))
            observed_candidates.extend(filtered["candidates"])
            return {
                "status": "completed",
                "evidence": ["results/specific-solution.md"],
                "receipt": {"artifact_path": str(artifact)},
            }

        with patch(
            "atlas.cash_first_usdc_cycle.run_verified_deliverable_cycle",
            side_effect=execute,
        ) as executor:
            outcome = run_cash_first_usdc_cycle(self.root)

        executor.assert_called_once_with(self.root)
        self.assertEqual([item["id"] for item in observed_candidates], ["eligible"])
        self.assertEqual(observed_candidates[0]["cash_first_reward_usdc"], 12)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["economic_gate"]["eligible"], 1)
        self.assertEqual(len(outcome["economic_gate"]["rejected"]), 3)
        self.assertEqual(json.loads(self.candidates_path.read_text(encoding="utf-8")), payload)

    def test_unverified_amount_fails_closed_before_execution(self) -> None:
        write_json(
            self.candidates_path,
            {"candidates": [candidate("unverified", 12, verified=False)]},
        )

        with patch("atlas.cash_first_usdc_cycle.run_verified_deliverable_cycle") as executor:
            outcome = run_cash_first_usdc_cycle(self.root)

        executor.assert_not_called()
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], "no_candidate_in_5_50_usdc_window")
        self.assertEqual(outcome["diagnosis"]["blocked_stage"], "economic_candidate_gate")

    def test_window_boundaries_are_inclusive(self) -> None:
        payload = {"candidates": [candidate("minimum", 5), candidate("maximum", 50)]}
        write_json(self.candidates_path, payload)
        observed_ids: list[str] = []

        def execute(root: Path) -> dict:
            filtered = json.loads(self.candidates_path.read_text(encoding="utf-8"))
            observed_ids.extend(item["id"] for item in filtered["candidates"])
            return {"status": "blocked", "reason": "acceptance_evidence_missing", "evidence": []}

        with patch(
            "atlas.cash_first_usdc_cycle.run_verified_deliverable_cycle",
            side_effect=execute,
        ):
            outcome = run_cash_first_usdc_cycle(self.root)

        self.assertEqual(observed_ids, ["minimum", "maximum"])
        self.assertEqual(outcome["economic_gate"]["eligible"], 2)
        self.assertEqual(json.loads(self.candidates_path.read_text(encoding="utf-8")), payload)

    def test_generic_draft_cannot_be_reported_as_completed(self) -> None:
        write_json(self.candidates_path, {"candidates": [candidate("eligible", 12)]})
        artifact = self.root / "deliverable.md"
        artifact.write_text(
            "# Draft deliverable — Small paid fix\n\n"
            "This is intended for iterative refinement against its acceptance criteria.\n",
            encoding="utf-8",
        )
        completed = {
            "status": "completed",
            "evidence": ["results/deliverable.md"],
            "receipt": {"artifact_path": str(artifact)},
        }

        with patch(
            "atlas.cash_first_usdc_cycle.run_verified_deliverable_cycle",
            return_value=completed,
        ):
            outcome = run_cash_first_usdc_cycle(self.root)

        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], "deliverable_not_acceptance_ready")
        self.assertEqual(outcome["diagnosis"]["blocked_stage"], "deliverable_quality_gate")


if __name__ == "__main__":
    unittest.main()
