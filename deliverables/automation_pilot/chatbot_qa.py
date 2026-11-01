"""Transparent checks of synthetic chatbot replies; not a semantic LLM judge."""
from __future__ import annotations

import json
from pathlib import Path


def evaluate(case: dict, approved_sources: set[str]) -> list[str]:
    response = case["response"]
    expected = case["expected"]
    issues = []
    if not isinstance(response, dict) or not isinstance(response.get("answer"), str):
        return ["invalid_response_schema"]
    answer = response["answer"].casefold()
    sources = response.get("source_ids")
    if (not isinstance(sources, list) or not all(isinstance(x, str) for x in sources)
            or not set(sources).issubset(approved_sources)):
        issues.append("unknown_or_invalid_source")
    elif not set(expected.get("required_sources", [])).issubset(sources):
        issues.append("required_source_missing")
    if type(response.get("escalate")) is not bool or response["escalate"] != expected["escalate"]:
        issues.append("escalation_mismatch")
    if response.get("action_taken") != "none":
        issues.append("unexpected_action_claim")
    for term in expected.get("must_include", []):
        if term.casefold() not in answer:
            issues.append("required_fact_missing:" + term)
    for term in expected.get("must_not_include", []):
        if term.casefold() in answer:
            issues.append("forbidden_claim:" + term)
    return issues


def report(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    rows = [{"case_id": case["id"], "issues": evaluate(case, set(fixture["knowledge_base"]))}
            for case in fixture["cases"]]
    return {"mode": "synthetic_fixture_replay_not_live_chatbot",
            "cases": len(rows), "flagged": sum(bool(row["issues"]) for row in rows),
            "manual_semantic_and_language_review_required": True,
            "customer_acceptance": False, "external_submission": False,
            "payment_verified": False, "results": rows}


if __name__ == "__main__":
    print(json.dumps(report(Path(__file__).with_name("chatbot_cases.json")), ensure_ascii=False, indent=2))
