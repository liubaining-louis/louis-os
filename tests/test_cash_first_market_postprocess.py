from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.cash_first_market_postprocess import attach_prepared_artifacts


class CashFirstMarketPostprocessTests(unittest.TestCase):
    def opportunity(self, *, status: str = "prepare_then_gate") -> dict:
        return {
            "opportunity_id": "market-one",
            "source_url": "https://example.test/job/one",
            "decision": {"status": status},
            "metadata": {
                "submission_dossier_required": True,
                "submission_dossier_prepared": False,
            },
        }

    def test_attaches_only_present_hash_verified_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "deliverables" / "solution.py"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("answer = 42\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            registry = {
                "items": [
                    {
                        "opportunity_id": "market-one",
                        "source_url": "https://example.test/job/one",
                        "artifact_paths": ["deliverables/solution.py"],
                        "sha256": {"deliverables/solution.py": digest},
                        "human_action_instructions": ["Review terms."],
                    }
                ]
            }
            result = attach_prepared_artifacts([self.opportunity()], registry, root=root)[0]
            self.assertTrue(result["metadata"]["submission_dossier_prepared"])
            self.assertTrue(result["metadata"]["prepared_artifact_registry_verified"])
            self.assertEqual(result["metadata"]["prepared_artifacts"], ["deliverables/solution.py"])

            registry["items"][0]["sha256"]["deliverables/solution.py"] = "0" * 64
            result = attach_prepared_artifacts([self.opportunity()], registry, root=root)[0]
            self.assertFalse(result["metadata"]["submission_dossier_prepared"])
            self.assertFalse(result["metadata"]["prepared_artifact_registry_verified"])

    def test_never_reactivates_a_rejected_opportunity(self) -> None:
        registry = {
            "items": [
                {
                    "opportunity_id": "market-one",
                    "source_url": "https://example.test/job/one",
                    "artifact_paths": ["anything"],
                }
            ]
        }
        result = attach_prepared_artifacts([self.opportunity(status="rejected")], registry)[0]
        self.assertFalse(result["metadata"]["submission_dossier_prepared"])


if __name__ == "__main__":
    unittest.main()
