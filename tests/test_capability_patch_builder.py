from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from atlas.capability_patch_builder import build_capability_patch_from_candidates


class CapabilityPatchBuilderTests(unittest.TestCase):
    def test_broken_link_patch_is_built_and_hashed(self) -> None:
        issue_url = "https://github.com/acme/docs/issues/5"
        responses = {
            "https://api.github.com/repos/acme/docs/issues/5": {
                "html_url": issue_url,
                "state": "open",
                "title": "Fix broken link",
                "body": "In `README.md`, replace https://old.example/docs with https://new.example/docs.",
                "labels": [{"name": "bounty"}],
            },
            "https://api.github.com/repos/acme/docs": {"default_branch": "main"},
            "https://api.github.com/repos/acme/docs/contents/README.md?ref=main": {
                "encoding": "base64",
                "content": base64.b64encode(b"See https://old.example/docs for details.\n").decode("ascii"),
            },
        }
        candidate = {"id": "link-fix", "url": issue_url, "external_prerequisites_cleared": True}
        with tempfile.TemporaryDirectory() as tmp:
            result = build_capability_patch_from_candidates([candidate], Path(tmp), responses.__getitem__)
            self.assertEqual(result.status, "patch_built")
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["patch_capability"]["capability_id"], "broken_link_replacement")
            self.assertTrue(manifest["tests_passed"])
            patched = Path(result.workspace) / manifest["files"][0]["content_path"]
            self.assertIn("https://new.example/docs", patched.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["files"][0]["sha256"]), 64)

    def test_json_configuration_patch_passes_syntax_validation(self) -> None:
        issue_url = "https://github.com/acme/app/issues/7"
        responses = {
            "https://api.github.com/repos/acme/app/issues/7": {
                "html_url": issue_url,
                "state": "open",
                "title": "Update configuration timeout",
                "body": "In `config.json`, set key `timeout` from `30` to `45`.",
                "labels": [{"name": "bounty"}],
            },
            "https://api.github.com/repos/acme/app": {"default_branch": "main"},
            "https://api.github.com/repos/acme/app/contents/config.json?ref=main": {
                "encoding": "base64",
                "content": base64.b64encode(b'{"timeout": 30, "enabled": true}\n').decode("ascii"),
            },
        }
        candidate = {"id": "config-fix", "url": issue_url, "external_prerequisites_cleared": True}
        with tempfile.TemporaryDirectory() as tmp:
            result = build_capability_patch_from_candidates([candidate], Path(tmp), responses.__getitem__)
            self.assertEqual(result.status, "patch_built")
            evidence = (Path(result.workspace) / "test_evidence.txt").read_text(encoding="utf-8")
            self.assertIn("json_syntax=passed", evidence)

    def test_invalid_json_result_is_rejected(self) -> None:
        issue_url = "https://github.com/acme/app/issues/8"
        responses = {
            "https://api.github.com/repos/acme/app/issues/8": {
                "html_url": issue_url,
                "state": "open",
                "title": "Update configuration",
                "body": 'In `config.json`, replace `30` with `oops}` for the failing configuration test.',
                "labels": [{"name": "bounty"}],
            },
            "https://api.github.com/repos/acme/app": {"default_branch": "main"},
            "https://api.github.com/repos/acme/app/contents/config.json?ref=main": {
                "encoding": "base64",
                "content": base64.b64encode(b'{"timeout": 30}\n').decode("ascii"),
            },
        }
        candidate = {"id": "bad-config", "url": issue_url, "external_prerequisites_cleared": True}
        with tempfile.TemporaryDirectory() as tmp:
            result = build_capability_patch_from_candidates([candidate], Path(tmp), responses.__getitem__)
        self.assertEqual(result.status, "blocked")


if __name__ == "__main__":
    unittest.main()
