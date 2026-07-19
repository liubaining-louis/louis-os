from scripts.autonomous_external_action_executor import is_low_risk_autonomous, validate_action


def base_action():
    return {
        "id": "a1",
        "candidate_id": "c1",
        "type": "github_issue_comment",
        "target_url": "https://github.com/example/project/issues/1",
        "body": "Tested result available.",
        "status": "prepared_pending_deliverable",
        "autonomy_class": "low_risk_reversible",
        "tested_deliverable": True,
        "evidence": ["https://github.com/example/project/actions/runs/1"],
        "guardrails": {
            "claims_revenue": False,
            "accepts_legal_terms": False,
            "spends_money": False,
            "creates_account": False,
            "uses_privileged_credentials": False,
            "destructive_or_irreversible": False,
            "discloses_sensitive_data": False,
        },
    }


def test_result_gate_accepts_tested_prepared_action():
    action = base_action()
    assert validate_action(action) == (True, "ok")
    assert is_low_risk_autonomous(action) is True


def test_money_or_legal_action_never_auto_authorized():
    for field in ("spends_money", "accepts_legal_terms", "creates_account"):
        action = base_action()
        action["guardrails"][field] = True
        assert is_low_risk_autonomous(action) is False


def test_untested_result_is_refused():
    action = base_action()
    action["tested_deliverable"] = False
    assert validate_action(action) == (False, "deliverable_not_tested")
