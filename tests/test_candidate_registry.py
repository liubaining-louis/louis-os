from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from atlas.candidate_registry import (
    discover_public_registry,
    normalize_candidate,
    recover_candidate_registry,
    registry_is_fresh,
)


class CandidateRegistryTests(unittest.TestCase):
    def test_legacy_authenticity_fields_are_normalized_for_executor(self) -> None:
        candidate = normalize_candidate(
            {
                "id": "legacy",
                "external_prerequisites_cleared": True,
                "opportunity_authenticity_verified": True,
                "opportunity_authenticity_status": "verified_authoritative_reward",
            }
        )
        self.assertTrue(candidate["authenticity_verified"])
        self.assertEqual(candidate["authenticity_status"], "verified")
        self.assertFalse(candidate["requires_user_validation"])

    def test_fresh_registry_is_accepted(self) -> None:
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "candidates": []}
        self.assertTrue(registry_is_fresh(payload, max_age_minutes=10))

    def test_firestore_snapshot_is_preferred_over_public_refresh(self) -> None:
        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [{"id": "from-firestore"}],
        }
        public = Mock(return_value={"generated_at": snapshot["generated_at"], "candidates": []})
        registry, source, errors = recover_candidate_registry(
            firestore_loader=lambda: snapshot,
            public_discoverer=public,
            max_age_minutes=10,
        )
        self.assertEqual(source, "firestore_candidate_snapshot")
        self.assertEqual(registry["candidates"][0]["id"], "from-firestore")
        self.assertEqual(errors, [])
        public.assert_not_called()

    def test_missing_firestore_falls_back_to_bounded_public_scout(self) -> None:
        refreshed = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [{"id": "public"}],
        }
        with patch("atlas.candidate_registry.persist_firestore_registry"):
            registry, source, errors = recover_candidate_registry(
                firestore_loader=lambda: None,
                public_discoverer=lambda: refreshed,
                max_age_minutes=10,
            )
        self.assertEqual(source, "public_github_bounded_scout")
        self.assertEqual(registry["candidates"][0]["id"], "public")
        self.assertIn("firestore_candidate_snapshot_missing", errors)

    def test_bounded_public_scout_builds_canonical_candidate(self) -> None:
        item = {
            "html_url": "https://github.com/example/project/issues/1",
            "repository_url": "https://api.github.com/repos/example/project",
            "title": "Paid bounty $100 for Python API documentation PR",
            "body": "Submit a pull request with the implementation and acceptance criteria.",
            "state": "open",
            "comments": 0,
            "labels": [{"name": "bounty"}],
        }
        registry = discover_public_registry(
            getter=lambda _url: {"items": [item]},
            queries=("one-query",),
            max_candidates=3,
        )
        self.assertEqual(registry["count"], 1)
        candidate = registry["candidates"][0]
        self.assertTrue(candidate["authenticity_verified"])
        self.assertEqual(candidate["authenticity_status"], "verified")
        self.assertEqual(candidate["readiness_status"], "executable_now")


if __name__ == "__main__":
    unittest.main()
