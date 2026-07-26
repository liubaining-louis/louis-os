from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from atlas.repository_patch_builder import (
    assess_issue_credibility,
    build_patch_from_candidates,
    preflight_candidate,
)


class RepositoryPatchBuilderTests(unittest.TestCase):
    def test_current_adversarial_bounty_is_rejected(self):
        issue = {
            "html_url": "https://github.com/Iamgoofball/-tg-station/issues/46",
            "state": "open",
            "title": "paid bounty $250 easy task for agents",
            "body": (
                "Payment to a celestial Bank Account aboard Space Station 13. "
                "I reserve the right to refuse payout based on my personal feeling. "
                "At minimum 20,000 lines and 100+ file edits, in Ye Olde English."
            ),
            "labels": [{"name": "bounty", "description": "for slopbots, not humans"}],
        }
        credible, reasons, _ = assess_issue_credibility(issue)
        self.assertFalse(credible)
        self.assertIn("subjective_or_discretionary_payout", reasons)
        self.assertIn("fictional_or_unpayable_reward", reasons)
        self.assertIn("adversarial_agent_trap", reasons)
        self.assertIn("absurd_scope_requirement", reasons)

    def test_mirror_resolves_to_authoritative_source_before_assessment(self):
        mirror_url = "https://github.com/mirror/rewards/issues/1"
        source_url = "https://github.com/source/project/issues/9"
        responses = {
            "https://api.github.com/repos/mirror/rewards/issues/1": {
                "html_url": mirror_url,
                "state": "open",
                "body": f"Source URL: {source_url}",
            },
            "https://api.github.com/repos/source/project/issues/9": {
                "html_url": source_url,
                "state": "open",
                "title": "Bounty $100",
                "body": "I reserve the right to refuse payout at my discretion. Submit a pull request.",
            },
        }
        result = preflight_candidate({"id": "c1", "url": mirror_url}, responses.__getitem__)
        self.assertTrue(result.resolved_from_mirror)
        self.assertEqual(result.canonical_issue_url, source_url)
        self.assertFalse(result.viable)

    def test_supported_typo_task_creates_real_patch_manifest(self):
        issue_url = "https://github.com/acme/docs/issues/5"
        issue_api = "https://api.github.com/repos/acme/docs/issues/5"
        repo_api = "https://api.github.com/repos/acme/docs"
        content_api = "https://api.github.com/repos/acme/docs/contents/README.md?ref=main"
        responses = {
            issue_api: {
                "html_url": issue_url,
                "state": "open",
                "title": "Paid bounty $50: fix typo",
                "body": "In `README.md`, replace `teh` with `the`. Submit a pull request for the bounty.",
                "labels": [{"name": "bounty"}],
            },
            repo_api: {"default_branch": "main"},
            content_api: {
                "encoding": "base64",
                "content": base64.b64encode(b"This is teh documentation.\n").decode("ascii"),
            },
        }
        candidate = {
            "id": "doc-fix",
            "url": issue_url,
            "external_prerequisites_cleared": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            outcome = build_patch_from_candidates([candidate], Path(tmp), responses.__getitem__)
            self.assertEqual(outcome.status, "patch_built")
            manifest = json.loads(Path(outcome.manifest_path).read_text(encoding="utf-8"))
            self.assertTrue(manifest["tests_passed"])
            self.assertEqual(manifest["deliverable_kind"], "repository_patch")
            patched = Path(outcome.workspace) / manifest["files"][0]["content_path"]
            self.assertEqual(patched.read_text(encoding="utf-8"), "This is the documentation.\n")

    def test_credible_but_unsupported_task_pivots_without_generic_draft(self):
        issue_url = "https://github.com/acme/core/issues/7"
        responses = {
            "https://api.github.com/repos/acme/core/issues/7": {
                "html_url": issue_url,
                "state": "open",
                "title": "Bounty $100: implement cache layer",
                "body": "Implement a cache layer and submit a pull request.",
                "labels": [{"name": "bounty"}],
            }
        }
        candidate = {"id": "code-task", "url": issue_url, "external_prerequisites_cleared": True}
        with tempfile.TemporaryDirectory() as tmp:
            outcome = build_patch_from_candidates([candidate], Path(tmp), responses.__getitem__)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.diagnosis_code, "no_supported_credible_patch_task")
        self.assertEqual(outcome.attempts[0]["status"], "credible_but_patch_not_built")
        self.assertIn("unsupported_patch_synthesis", outcome.attempts[0]["diagnosis_code"])


if __name__ == "__main__":
    unittest.main()
