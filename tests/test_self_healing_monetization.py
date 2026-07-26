from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from atlas.self_healing_monetization import run_self_healing_deliverable_cycle


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def recovered_registry() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": [
            {
                "id": "recovered-1",
                "title": "Paid Python API documentation bounty",
                "body": "Create a Python API guide and submit a pull request.",
                "url": "https://github.com/example/project/issues/1",
                "readiness_status": "executable_now",
                "external_prerequisites_cleared": True,
                "requires_user_validation": False,
                "authenticity_verified": True,
                "authenticity_status": "verified",
                "execution_score": 90,
                "score": 80,
            }
        ],
    }


class SelfHealingMonetizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.results.mkdir(parents=True)
        write_json(
            self.results / "monetization.json",
            {"revenue_confirmed_eur": 0, "external_actions_submitted": 0},
        )

    def test_missing_registry_is_repaired_and_execution_retries_immediately(self) -> None:
        outcome = run_self_healing_deliverable_cycle(
            self.root,
            recoverer=lambda: (recovered_registry(), "firestore_candidate_snapshot", []),
            enable_external_recovery=True,
        )
        self.assertEqual(outcome["status"], "completed")
        self.assertTrue(outcome["automatic_retry_performed"])
        self.assertEqual(outcome["candidate_registry_recovery"]["source"], "firestore_candidate_snapshot")
        self.assertTrue((self.results / "monetization_candidates.json").is_file())
        self.assertTrue((self.results / "candidate_registry_recovery.json").is_file())
        self.assertIn("results/candidate_registry_recovery.json", outcome["evidence"])

    def test_legacy_local_registry_is_normalized_without_network(self) -> None:
        legacy = recovered_registry()
        candidate = legacy["candidates"][0]
        candidate.pop("authenticity_verified")
        candidate.pop("authenticity_status")
        candidate["opportunity_authenticity_verified"] = True
        candidate["opportunity_authenticity_status"] = "verified_authoritative_reward"
        write_json(self.results / "monetization_candidates.json", legacy)

        outcome = run_self_healing_deliverable_cycle(
            self.root,
            enable_external_recovery=False,
        )
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["candidate_registry_recovery"]["source"], "local_schema_normalization")
        normalized = json.loads((self.results / "monetization_candidates.json").read_text())
        self.assertTrue(normalized["candidates"][0]["authenticity_verified"])
        self.assertEqual(normalized["candidates"][0]["authenticity_status"], "verified")

    def test_failed_recovery_returns_evidence_backed_blocker(self) -> None:
        outcome = run_self_healing_deliverable_cycle(
            self.root,
            recoverer=lambda: (None, "unavailable", ["firestore_missing", "public_scout_failed"]),
            enable_external_recovery=True,
        )
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], "candidate_file_unavailable")
        self.assertTrue(outcome["candidate_registry_recovery"]["attempted"])
        self.assertIn("results/candidate_registry_recovery.json", outcome["evidence"])


if __name__ == "__main__":
    unittest.main()
