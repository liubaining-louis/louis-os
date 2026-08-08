from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.superteam_crypto_cycle import run_superteam_crypto_cycle


class SuperteamCryptoCycleTests(unittest.TestCase):
    def test_missing_key_blocks_without_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("atlas.superteam_crypto_cycle._api_key", return_value=""):
            out = run_superteam_crypto_cycle(Path(tmp))
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(out["reason"], "superteam_api_key_missing")

    def test_eligible_listing_without_package_returns_prepare_then_gate(self) -> None:
        payload = {"listings": [{"id": "b1", "agentAccess": "AGENT_ONLY", "rewardAmount": 500}]}
        with tempfile.TemporaryDirectory() as tmp, patch("atlas.superteam_crypto_cycle._api_key", return_value="k"), patch("atlas.superteam_crypto_cycle.live_listings", return_value=payload):
            out = run_superteam_crypto_cycle(Path(tmp))
        self.assertEqual(out["reason"], "prepare_then_gate")
        self.assertEqual(out["execution_mode"], "deterministic_superteam_executor")

    def test_valid_package_submits_and_records_receipt(self) -> None:
        payload = {"listings": [{"id": "b1", "agentAccess": "AGENT_ALLOWED", "rewardAmount": 250}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "superteam_submission_package.json").write_text(json.dumps({"listingId": "b1", "link": "https://github.com/example/repo", "otherInfo": "A complete tested implementation with documentation and reproducible instructions."}), encoding="utf-8")
            with patch("atlas.superteam_crypto_cycle._api_key", return_value="k"), patch("atlas.superteam_crypto_cycle.live_listings", return_value=payload), patch("atlas.superteam_crypto_cycle.create_submission", return_value={"id": "submission-1"}) as submit:
                out = run_superteam_crypto_cycle(root)
            self.assertEqual(out["status"], "completed")
            self.assertEqual(out["result"], "verified_external_submission")
            submit.assert_called_once()
            self.assertTrue((results / "superteam_submission_receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
