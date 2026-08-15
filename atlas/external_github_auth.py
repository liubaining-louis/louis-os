"""Credential policy for GitHub writes outside the Louis OS repository.

GitHub Actions' automatic ``GITHUB_TOKEN`` is an installation token. It is
intentionally excluded here because it cannot write to unrelated repositories
where the GitHub App is not installed. External writes must use a user-owned
PAT so public attribution and permissions are explicit.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

PRIMARY_ENV = "LOUIS_GITHUB_PAT"
LEGACY_ENV = "ATLAS_EXTERNAL_GITHUB_TOKEN"


class ExternalGitHubCredentialMissing(RuntimeError):
    """Raised when no user-owned credential is available for an external write."""


def external_github_token(environ: Mapping[str, str] | None = None) -> str:
    """Return the PAT used for external GitHub mutations.

    ``LOUIS_GITHUB_PAT`` is the canonical secret. The previous
    ``ATLAS_EXTERNAL_GITHUB_TOKEN`` remains supported for a migration period.
    ``GITHUB_TOKEN`` is deliberately never considered.
    """

    env = os.environ if environ is None else environ
    token = (env.get(PRIMARY_ENV) or env.get(LEGACY_ENV) or "").strip()
    if not token:
        raise ExternalGitHubCredentialMissing(
            "external_github_pat_missing: configure LOUIS_GITHUB_PAT "
            "(preferred) or legacy ATLAS_EXTERNAL_GITHUB_TOKEN; "
            "GITHUB_TOKEN is intentionally excluded from external writes"
        )
    return token


def external_github_credential_source(environ: Mapping[str, str] | None = None) -> str:
    """Return the environment variable supplying the active external identity."""

    env = os.environ if environ is None else environ
    if (env.get(PRIMARY_ENV) or "").strip():
        return PRIMARY_ENV
    if (env.get(LEGACY_ENV) or "").strip():
        return LEGACY_ENV
    raise ExternalGitHubCredentialMissing("external_github_pat_missing")
