from atlas.monetization_focus import select_execution_focus


def candidate(candidate_id: str, score: int = 100) -> dict:
    return {
        "id": candidate_id,
        "score": score,
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
    }


def test_active_execution_cannot_be_replaced_by_new_top_candidate() -> None:
    decision = select_execution_focus(
        candidates=[candidate("new-top")],
        approvals=[],
        execution_receipts=[{
            "candidate_id": "already-started",
            "action": "internal_execution_issue_created",
            "external_submission": False,
        }],
    )

    assert decision.candidate_id == "already-started"
    assert decision.reason == "active_execution_locked"
    assert decision.should_create_internal_issue is False


def test_approved_candidate_beats_unapproved_higher_ranked_candidate() -> None:
    decision = select_execution_focus(
        candidates=[candidate("new-top"), candidate("approved")],
        approvals=[{
            "candidate_id": "approved",
            "status": "approved",
            "consumed_at": None,
        }],
        execution_receipts=[],
    )

    assert decision.candidate_id == "approved"
    assert decision.reason == "approved_candidate_preferred"
    assert decision.should_create_internal_issue is True


def test_falls_back_to_first_executable_candidate() -> None:
    decision = select_execution_focus(
        candidates=[candidate("top")],
        approvals=[],
        execution_receipts=[],
    )

    assert decision.candidate_id == "top"
    assert decision.reason == "highest_ranked_executable_candidate"


def test_completed_or_abandoned_receipt_does_not_lock_pipeline() -> None:
    decision = select_execution_focus(
        candidates=[candidate("next")],
        approvals=[],
        execution_receipts=[{
            "candidate_id": "old",
            "action": "internal_execution_issue_created",
            "external_submission": False,
            "abandoned": True,
        }],
    )

    assert decision.candidate_id == "next"
    assert decision.should_create_internal_issue is True
