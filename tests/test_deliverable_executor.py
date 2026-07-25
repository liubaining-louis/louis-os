import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from atlas.deliverable_executor import execute_candidate, infer_deliverable_type, validate_candidate


def candidate(**overrides):
    value = {
        "id": "abc123",
        "title": "Paid Python API documentation bounty",
        "body": "Create a Python API guide and submit a pull request.",
        "url": "https://github.com/example/project/issues/1",
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
        "requires_user_validation": False,
        "authenticity_verified": True,
    }
    value.update(overrides)
    return value


class DeliverableExecutorTests(unittest.TestCase):
    def test_infers_documentation_before_script(self):
        self.assertEqual(infer_deliverable_type(candidate()), "documentation")

    def test_execute_creates_hashed_artifact_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            receipt = execute_candidate(candidate(), Path(tmp_dir))
            artifact = Path(receipt.artifact_path)
            manifest = json.loads(Path(receipt.manifest_path).read_text(encoding="utf-8"))

            self.assertEqual(receipt.status, "deliverable_created")
            self.assertFalse(receipt.externally_submitted)
            self.assertTrue(artifact.exists())
            self.assertEqual(receipt.artifact_sha256, hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(manifest["status"], "deliverable_created")
            self.assertFalse(manifest["externally_submitted"])
            self.assertIsNone(manifest["external_receipt"])
            self.assertTrue((artifact.parent / "execution_receipt.json").exists())
            self.assertTrue((artifact.parent / "SCOPE.md").exists())

    def test_rejects_ineligible_candidates(self):
        cases = [
            ({"readiness_status": "gated"}, "candidate_not_executable_now"),
            ({"external_prerequisites_cleared": False}, "external_prerequisites_not_cleared"),
            ({"requires_user_validation": True}, "candidate_requires_user_validation"),
            ({"authenticity_verified": False, "authenticity_status": "blocked"}, "candidate_authenticity_not_verified"),
        ]
        for changes, reason in cases:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, reason):
                    validate_candidate(candidate(**changes))

    def test_script_artifact_is_concrete_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            receipt = execute_candidate(
                candidate(title="Paid Python automation script", body="Implement a Python CLI automation."),
                Path(tmp_dir),
            )
            artifact = Path(receipt.artifact_path)
            source = artifact.read_text(encoding="utf-8")
            self.assertEqual(artifact.name, "solution.py")
            self.assertIn("def solve(payload: dict) -> dict:", source)
            self.assertNotIn("Not submitted", source)
            self.assertEqual(receipt.artifact_sha256, hashlib.sha256(artifact.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
