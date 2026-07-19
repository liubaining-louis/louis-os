from scripts import sync_operational_state_to_firestore as sync


def test_build_state_removes_stale_validation_and_prefers_prepared_work(monkeypatch):
    fixtures = {
        "monetization.json": {
            "execution_status": "implementation_ticket_opened",
            "next_action": "old action",
            "top_opportunity": {
                "id": "abc",
                "title": "Candidate",
                "requires_user_validation": True,
            },
        },
        "monetization_candidates.json": {"count": 1, "candidates": []},
        "external_action_queue.json": {
            "actions": [{"id": "a1", "status": "prepared_pending_deliverable"}]
        },
        "external_action_receipts.json": {"receipts": []},
    }
    monkeypatch.setattr(sync, "load_json", lambda name, default: fixtures.get(name, default))

    state = sync.build_operational_state("2026-07-19T20:00:00+00:00")

    assert state["requires_user_validation"] is False
    assert state["human_gate_pending"] is False
    assert state["autonomy_policy"] == "result_first_autonomy"
    assert state["execution_status"] == "building_tested_deliverable"
    assert "requires_user_validation" not in state["top_candidate"]
    assert state["top_candidate"]["manual_validation_required"] is False


def test_verified_receipt_has_priority(monkeypatch):
    fixtures = {
        "monetization.json": {},
        "monetization_candidates.json": {"count": 0, "candidates": []},
        "external_action_queue.json": {"actions": []},
        "external_action_receipts.json": {
            "receipts": [{"action_id": "a1", "verified": True, "receipt_url": "https://github.com/x"}]
        },
    }
    monkeypatch.setattr(sync, "load_json", lambda name, default: fixtures.get(name, default))

    state = sync.build_operational_state("2026-07-19T20:00:00+00:00")

    assert state["execution_status"] == "external_action_verified"
    assert state["external_receipts_verified"] == 1
