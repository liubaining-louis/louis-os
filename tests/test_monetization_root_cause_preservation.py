from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.repository_patch_builder import PatchBuildResult
from scripts import autonomous_submission_package_builder as package_builder
from scripts import autonomous_target_patch_builder as target_builder


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class MonetizationRootCausePreservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.results.mkdir(parents=True)

    def test_target_patch_stage_preserves_empty_registry_root_cause(self) -> None:
        candidates = self.results / "monetization_candidates.json"
        ledger = self.results / "monetization.json"
        preflight = self.results / "target_preflight.json"
        workspaces = self.results / "target_repository_workspaces"
        write_json(
            candidates,
            {
                "candidates": [],
                "root_cause_code": "no_final_safe_convertible_payable_candidate",
                "credible_backlog_count": 0,
            },
        )
        write_json(
            ledger,
            {
                "root_cause_code": "no_final_safe_convertible_payable_candidate",
                "primary_blocker": "No task survived the final gate.",
                "next_action": "expand_verified_provider_sources_and_refresh",
            },
        )
        blocked = PatchBuildResult(
            status="blocked",
            candidate_id=None,
            workspace=None,
            manifest_path=None,
            diagnosis_code="no_supported_credible_patch_task",
            attempts=(),
        )
        with (
            patch.object(target_builder, "CANDIDATES_PATH", candidates),
            patch.object(target_builder, "LEDGER_PATH", ledger),
            patch.object(target_builder, "PREFLIGHT_PATH", preflight),
            patch.object(target_builder, "WORKSPACES", workspaces),
            patch.object(target_builder, "build_patch_from_candidates", return_value=blocked),
        ):
            self.assertEqual(target_builder.main(), 0)

        state = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(state["root_cause_code"], "no_final_safe_convertible_payable_candidate")
        self.assertEqual(state["execution_status"], "no_final_safe_convertible_payable_candidate")
        self.assertEqual(state["downstream_patch_stage"], "skipped_no_candidate")
        diagnostic = json.loads(preflight.read_text(encoding="utf-8"))
        self.assertTrue(diagnostic["upstream_root_cause_preserved"])

    def test_package_stage_does_not_replace_discovery_blocker(self) -> None:
        ledger = self.results / "monetization.json"
        package = self.results / "submission_package.json"
        diagnosis = self.results / "submission_diagnosis.json"
        write_json(
            ledger,
            {
                "root_cause_code": "no_final_safe_convertible_payable_candidate",
                "execution_status": "no_final_safe_convertible_payable_candidate",
                "primary_blocker": "No task survived the final gate.",
                "next_action": "expand_verified_provider_sources_and_refresh",
                "top_opportunity": None,
            },
        )
        with (
            patch.object(package_builder, "RESULTS", self.results),
            patch.object(package_builder, "LEDGER_PATH", ledger),
            patch.object(package_builder, "PACKAGE_PATH", package),
            patch.object(package_builder, "DIAGNOSIS_PATH", diagnosis),
        ):
            self.assertEqual(package_builder.main(), 0)

        state = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(state["root_cause_code"], "no_final_safe_convertible_payable_candidate")
        self.assertEqual(state["execution_status"], "no_final_safe_convertible_payable_candidate")
        self.assertEqual(state["downstream_package_stage"], "skipped_no_candidate")
        diagnostic = json.loads(diagnosis.read_text(encoding="utf-8"))
        self.assertEqual(diagnostic["blocked_stage"], "opportunity_discovery")
        self.assertTrue(diagnostic["upstream_root_cause_preserved"])


if __name__ == "__main__":
    unittest.main()
