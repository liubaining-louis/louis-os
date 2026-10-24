"""Receipt-backed external submission executor.

The executor fails closed. It can prepare and dry-run any supported platform adapter,
but only marks an external submission verified when the adapter returns a non-empty,
platform-issued receipt id and canonical confirmation URL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class SubmissionAuthorization:
    authorization_id: str
    dossier_id: str
    platform: str
    approved: bool
    approved_at: str
    scope: str = "single_submission"


@dataclass(frozen=True)
class SubmissionReceipt:
    platform: str
    opportunity_id: str
    dossier_id: str
    receipt_id: str
    confirmation_url: str
    submitted_at: str
    payload_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionResult:
    status: str
    externally_submitted: bool
    external_submission_verified: bool
    blocker: str | None
    receipt: SubmissionReceipt | None
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["receipt"] = self.receipt.to_dict() if self.receipt else None
        return payload


class SubmissionAdapter(Protocol):
    platform: str

    def revalidate(self, dossier: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def submit(self, dossier: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _hash_payload(dossier: Mapping[str, Any]) -> str:
    canonical = "|".join(
        str(dossier.get(key, ""))
        for key in ("dossier_id", "opportunity_id", "canonical_url", "proposal_text", "reward_amount", "currency")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def preflight(dossier: Mapping[str, Any], authorization: SubmissionAuthorization | None) -> tuple[bool, str | None]:
    required = ("dossier_id", "opportunity_id", "canonical_url", "proposal_text")
    if any(not str(dossier.get(key, "")).strip() for key in required):
        return False, "incomplete_dossier"
    if dossier.get("status") != "prepare_then_gate":
        return False, "dossier_not_gated"
    if not _valid_https_url(str(dossier.get("canonical_url"))):
        return False, "invalid_canonical_url"
    if dossier.get("external_submission_verified") is True:
        return False, "already_verified"
    if not authorization or not authorization.approved:
        return False, "explicit_authorization_required"
    if authorization.dossier_id != dossier.get("dossier_id"):
        return False, "authorization_dossier_mismatch"
    if authorization.scope != "single_submission":
        return False, "authorization_scope_invalid"
    return True, None


def execute_submission(
    dossier: Mapping[str, Any],
    adapter: SubmissionAdapter,
    authorization: SubmissionAuthorization | None,
    *,
    dry_run: bool = True,
) -> SubmissionResult:
    ok, blocker = preflight(dossier, authorization)
    if not ok:
        return SubmissionResult("blocked", False, False, blocker, None, ())
    if adapter.platform.casefold() != str(authorization.platform).casefold():
        return SubmissionResult("blocked", False, False, "authorization_platform_mismatch", None, ())

    verification = dict(adapter.revalidate(dossier))
    if verification.get("listing_open") is not True:
        return SubmissionResult("blocked", False, False, "listing_not_open", None, tuple(verification.get("evidence", ()) or ()))
    if verification.get("remote_eligible") is not True:
        return SubmissionResult("blocked", False, False, "remote_ineligible", None, tuple(verification.get("evidence", ()) or ()))
    if verification.get("platform_compliant") is not True:
        return SubmissionResult("blocked", False, False, "platform_policy_blocked", None, tuple(verification.get("evidence", ()) or ()))

    if dry_run:
        return SubmissionResult(
            "dry_run_ready",
            False,
            False,
            None,
            None,
            tuple(verification.get("evidence", ()) or ()) + ("dry_run:no_external_action",),
        )

    response = dict(adapter.submit(dossier))
    receipt_id = str(response.get("receipt_id") or "").strip()
    confirmation_url = str(response.get("confirmation_url") or "").strip()
    submitted_at = str(response.get("submitted_at") or datetime.now(timezone.utc).isoformat())
    evidence = tuple(response.get("evidence", ()) or ())

    if not receipt_id or not _valid_https_url(confirmation_url):
        return SubmissionResult("attempted_unverified", True, False, "missing_platform_receipt", None, evidence)

    receipt = SubmissionReceipt(
        platform=adapter.platform,
        opportunity_id=str(dossier["opportunity_id"]),
        dossier_id=str(dossier["dossier_id"]),
        receipt_id=receipt_id,
        confirmation_url=confirmation_url,
        submitted_at=submitted_at,
        payload_hash=_hash_payload(dossier),
    )
    return SubmissionResult("submitted_verified", True, True, None, receipt, evidence)
