from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from atlas.monetization_execution_cycle import run_verified_deliverable_cycle


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def verified_candidate(**overrides):
    value = {
        "id": "candidate-1",
        "title": "Paid Python API documentation bounty",
        "body": "Create a Python API guide.",
        "url": "https://github.com/example/project/issues/1",
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
        "requires_user_validation": False,
        "authenticity_verified": True,
        "authenticity_status": "verified",
        "execution_score": 90,
        "score": 80,
    }
    value.update(overrides)
    return value


class MonetizationExecutionCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.results.mkdir(parents=True)
        write_json(
            self.results / "monetization.json",
            {
                "revenue_confirmed_eur": 0,
                "external_actions_submitted": 0,
                "internal_execution_actions": 0,
            },
        )

    def test_cycle_creates_and_verifies_concrete_evidence(self) -> None:
        write_json(
            self.results / "monetization_candidates.json",
            {"candidates": [verified_candidate()]},
        )

        outcome = run_verified_deliverable_cycle(self.root)

        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["execution_mode"], "deterministic_internal_executor")
        self.assertGreaterEqual(len(outcome["evidence"]), 5)
        receipt = outcome["receipt"]
        artifact = Path(receipt["artifact_path"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(receipt["artifact_sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.assertEqual(outcome["revenue_confirmed_eur"], 0)
        self.assertEqual(outcome["external_actions_submitted"], 0)

    def test_stale_unverified_candidates_produce_causal_blockage(self) -> None:
        stale = verified_candidate()
        stale.pop("authenticity_verified")
        stale.pop("authenticity_status")
        write_json(self.results / "monetization_candidates.json", {"candidates": [stale]})

        outcome = run_verified_deliverable_cycle(self.root)

        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], "no_authentic_executable_candidate")
        self.assertEqual(outcome["diagnosis"]["resolution_class"], "AUTO_RESOLVABLE")
        self.assertIn("authenticity", outcome["diagnosis"]["direct_cause"])
        self.assertTrue(outcome["evidence"])
        ledger = json.loads((self.results / "monetization.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["root_cause_code"], "no_authentic_executable_candidate")

    def test_missing_candidate_registry_is_diagnosed_not_hallucinated(self) -> None:
        outcome = run_verified_deliverable_cycle(self.root)

        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], "candidate_file_unavailable")
        self.assertEqual(outcome["diagnosis"]["blocked_stage"], "candidate_loading")
        self.assertNotEqual(outcome["diagnosis"]["next_action"], "ask_user_what_to_do")


if __name__ == "__main__":
    unittest.main()
