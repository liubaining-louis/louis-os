from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FocusDecision:
    candidate_id: str | None
    reason: str
    should_create_internal_issue: bool


def _is_executable(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("readiness_status") == "executable_now"
        and candidate.get("external_prerequisites_cleared") is True
    )


def select_execution_focus(
    *,
    candidates: Sequence[Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]],
    execution_receipts: Sequence[Mapping[str, Any]],
) -> FocusDecision:
    """Choose one monetization candidate and prevent candidate churn.

    An already-started candidate remains the focus until a later workflow records
    an external submission, a verified abandonment, or closes the execution ticket.
    Otherwise, an explicitly approved executable candidate is preferred over the
    current discovery ranking.
    """
    active_receipts = [
        receipt
        for receipt in execution_receipts
        if receipt.get("candidate_id")
        and receipt.get("action") == "internal_execution_issue_created"
        and receipt.get("external_submission") is False
        and receipt.get("abandoned") is not True
    ]
    if active_receipts:
        return FocusDecision(
            candidate_id=str(active_receipts[-1]["candidate_id"]),
            reason="active_execution_locked",
            should_create_internal_issue=False,
        )

    candidate_by_id = {
        str(candidate.get("id")): candidate
        for candidate in candidates
        if candidate.get("id") and _is_executable(candidate)
    }
    for approval in reversed(approvals):
        candidate_id = str(approval.get("candidate_id") or "")
        if (
            candidate_id in candidate_by_id
            and approval.get("status") == "approved"
            and not approval.get("consumed_at")
        ):
            return FocusDecision(
                candidate_id=candidate_id,
                reason="approved_candidate_preferred",
                should_create_internal_issue=True,
            )

    for candidate in candidates:
        if candidate.get("id") and _is_executable(candidate):
            return FocusDecision(
                candidate_id=str(candidate["id"]),
                reason="highest_ranked_executable_candidate",
                should_create_internal_issue=True,
            )

    return FocusDecision(
        candidate_id=None,
        reason="no_executable_candidate",
        should_create_internal_issue=False,
    )
