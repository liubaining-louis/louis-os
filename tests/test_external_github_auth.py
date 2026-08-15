from __future__ import annotations

import unittest

from atlas.external_github_auth import (
    ExternalGitHubCredentialMissing,
    external_github_credential_source,
    external_github_token,
)
from atlas.autonomous_submission import GitHubClient, diagnose_submission_failure


class ExternalGitHubAuthTests(unittest.TestCase):
    def test_louis_pat_has_priority(self):
        env = {
            "LOUIS_GITHUB_PAT": "new-pat",
            "ATLAS_EXTERNAL_GITHUB_TOKEN": "legacy-pat",
            "GITHUB_TOKEN": "actions-installation-token",
        }
        self.assertEqual(external_github_token(env), "new-pat")
        self.assertEqual(external_github_credential_source(env), "LOUIS_GITHUB_PAT")

    def test_legacy_pat_remains_supported_during_migration(self):
        env = {
            "ATLAS_EXTERNAL_GITHUB_TOKEN": "legacy-pat",
            "GITHUB_TOKEN": "actions-installation-token",
        }
        self.assertEqual(external_github_token(env), "legacy-pat")
        self.assertEqual(external_github_credential_source(env), "ATLAS_EXTERNAL_GITHUB_TOKEN")

    def test_actions_github_token_is_never_an_external_write_fallback(self):
        with self.assertRaisesRegex(ExternalGitHubCredentialMissing, "external_github_pat_missing"):
            external_github_token({"GITHUB_TOKEN": "actions-installation-token"})

    def test_explicit_pat_can_be_injected_into_client(self):
        client = GitHubClient(token="explicit-pat")
        self.assertEqual(client.token, "explicit-pat")

    def test_missing_pat_diagnosis_routes_to_email_fallback(self):
        diagnosis = diagnose_submission_failure(
            ExternalGitHubCredentialMissing("external_github_pat_missing")
        )
        self.assertEqual(diagnosis.status, "blocked")
        self.assertEqual(diagnosis.resolution_class, "CAPABILITY_REQUIRED")
        self.assertEqual(
            diagnosis.next_action,
            "use_documented_email_fallback_or_configure_LOUIS_GITHUB_PAT",
        )

    def test_403_diagnosis_does_not_retry_with_actions_token(self):
        diagnosis = diagnose_submission_failure(RuntimeError("github_http_403:Resource not accessible by integration"))
        self.assertEqual(diagnosis.status, "blocked")
        self.assertEqual(
            diagnosis.next_action,
            "use_documented_email_fallback_or_rotate_LOUIS_GITHUB_PAT",
        )


if __name__ == "__main__":
    unittest.main()
