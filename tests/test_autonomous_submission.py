from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from atlas.autonomous_submission import diagnose_submission_failure, submit_patch, validate_patch_manifest


class FakeGitHub:
    def __init__(self, direct_push: bool = False):
        self.direct_push = direct_push
        self.calls = []

    def current_user(self):
        return "atlas-bot"

    def repository(self, full_name):
        self.calls.append(("repository", full_name))
        return {"default_branch": "main", "permissions": {"push": self.direct_push}}

    def ensure_fork(self, upstream, login):
        self.calls.append(("fork", upstream, login))
        return f"{login}/{upstream.split('/', 1)[1]}"

    def ref_sha(self, full_name, branch):
        self.calls.append(("ref", full_name, branch))
        return "base-sha"

    def ensure_branch(self, full_name, branch, base_sha):
        self.calls.append(("branch", full_name, branch, base_sha))

    def put_file(self, full_name, branch, target_path, source, message):
        self.calls.append(("put", full_name, branch, target_path))
        return {"path": target_path, "commit_sha": "commit-1", "content_sha": "content-1"}

    def create_pull_request(self, upstream, head, base, title, body):
        self.calls.append(("pr", upstream, head, base))
        return {"html_url": "https://github.com/example/project/pull/2", "number": 2}

    def comment_issue(self, upstream, issue_number, body):
        self.calls.append(("comment", upstream, issue_number))
        return {"html_url": "https://github.com/example/project/issues/1#issuecomment-1", "id": 1}


class AutonomousSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        patch = self.workspace / "patches" / "README.md"
        patch.parent.mkdir(parents=True)
        patch.write_text("# tested patch\n", encoding="utf-8")
        evidence = self.workspace / "tests.log"
        evidence.write_text("1 passed\n", encoding="utf-8")
        self.manifest = {
            "candidate_id": "candidate-1",
            "target_issue_url": "https://github.com/example/project/issues/1",
            "target_repository": "example/project",
            "base_branch": "main",
            "branch_name": "atlas/candidate-1",
            "pr_title": "Fix candidate 1",
            "pr_body": "Closes #1\n\nTests: 1 passed.",
            "deliverable_kind": "repository_patch",
            "tests_passed": True,
            "test_commands": ["python -m unittest"],
            "test_evidence": ["tests.log"],
            "files": [{
                "path": "README.md",
                "content_path": "patches/README.md",
                "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            }],
            "requires_cla": False,
            "requires_dco": False,
            "requires_new_account": False,
            "requires_payment_or_fee": False,
            "requires_kyc": False,
        }
        self.manifest_path = self.workspace / "patch_manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_manifest_verifies_file_hashes_and_tests(self):
        verified = validate_patch_manifest(self.manifest, self.workspace)
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["path"], "README.md")

    def test_generic_draft_fails_closed(self):
        generic = dict(self.manifest, deliverable_kind="documentation")
        with self.assertRaisesRegex(ValueError, "generic_deliverable_not_submittable"):
            validate_patch_manifest(generic, self.workspace)
        diagnosis = diagnose_submission_failure(ValueError("generic_deliverable_not_submittable"))
        self.assertEqual(diagnosis.resolution_class, "AUTO_RESOLVABLE")
        self.assertEqual(diagnosis.next_action, "inspect_target_repository_and_build_tested_patch_manifest")

    def test_legal_identity_and_payment_gates_fail_closed(self):
        for field in ("requires_cla", "requires_dco", "requires_new_account", "requires_payment_or_fee", "requires_kyc"):
            with self.subTest(field=field):
                value = dict(self.manifest)
                value[field] = True
                with self.assertRaises(ValueError):
                    validate_patch_manifest(value, self.workspace)

    def test_fork_branch_commit_pr_and_issue_receipts_are_recorded(self):
        client = FakeGitHub(direct_push=False)
        receipt = submit_patch(self.manifest_path, self.workspace, client=client)
        self.assertEqual(receipt["status"], "submitted")
        self.assertEqual(receipt["repository_mode"], "fork")
        self.assertEqual(receipt["source_repository"], "atlas-bot/project")
        self.assertEqual(receipt["pull_request_number"], 2)
        self.assertTrue(receipt["verified"])
        self.assertIn(("fork", "example/project", "atlas-bot"), client.calls)
        self.assertIn(("comment", "example/project", 1), client.calls)

    def test_direct_push_uses_target_repository_without_fork(self):
        client = FakeGitHub(direct_push=True)
        receipt = submit_patch(self.manifest_path, self.workspace, client=client)
        self.assertEqual(receipt["repository_mode"], "direct_push")
        self.assertEqual(receipt["source_repository"], "example/project")
        self.assertFalse(any(call[0] == "fork" for call in client.calls))


if __name__ == "__main__":
    unittest.main()
