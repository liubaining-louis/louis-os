from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import autonomous_pull_request_submitter as submitter


class SubmitterRootCausePreservationTests(unittest.TestCase):
    def test_missing_package_does_not_replace_final_discovery_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            ledger = results / "monetization.json"
            diagnosis = results / "submission_diagnosis.json"
            package = results / "submission_package.json"
            receipts = results / "submission_receipts.json"
            ledger.write_text(
                json.dumps(
                    {
                        "root_cause_code": "no_final_safe_convertible_payable_candidate",
                        "execution_status": "no_final_safe_convertible_payable_candidate",
                        "primary_blocker": "No candidate survived final discovery.",
                        "next_action": "expand_verified_provider_sources_and_refresh",
                        "top_opportunity": None,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(submitter, "ROOT", root),
                patch.object(submitter, "RESULTS", results),
                patch.object(submitter, "PACKAGE_PATH", package),
                patch.object(submitter, "RECEIPTS_PATH", receipts),
                patch.object(submitter, "DIAGNOSIS_PATH", diagnosis),
                patch.object(submitter, "LEDGER_PATH", ledger),
            ):
                self.assertEqual(submitter.main(), 0)

            state = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(state["root_cause_code"], "no_final_safe_convertible_payable_candidate")
            self.assertEqual(state["execution_status"], "no_final_safe_convertible_payable_candidate")
            self.assertEqual(state["downstream_submitter_stage"], "skipped_no_candidate")
            self.assertEqual(state["next_action"], "expand_verified_provider_sources_and_refresh")
            diagnostic = json.loads(diagnosis.read_text(encoding="utf-8"))
            self.assertEqual(diagnostic["blocked_stage"], "opportunity_discovery")
            self.assertTrue(diagnostic["upstream_root_cause_preserved"])


if __name__ == "__main__":
    unittest.main()
