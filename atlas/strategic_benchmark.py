from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.strategic_decision import CandidateAction, RiskAssessment, select_strategic_action


@dataclass(frozen=True)
class BenchmarkResult:
    version: str
    passed: bool
    passed_cases: int
    total_cases: int
    failures: tuple[str, ...]


def _risk(payload: dict[str, Any]) -> RiskAssessment:
    return RiskAssessment(
        technical=int(payload.get("technical", 0)),
        legal=int(payload.get("legal", 0)),
        commercial=int(payload.get("commercial", 0)),
        reputational=int(payload.get("reputational", 0)),
        safety=int(payload.get("safety", 0)),
    )


def _action(payload: dict[str, Any]) -> CandidateAction:
    return CandidateAction(
        action_id=str(payload["action_id"]),
        goal_ids=tuple(str(item) for item in payload["goal_ids"]),
        evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
        expected_value=float(payload["expected_value"]),
        confidence=float(payload["confidence"]),
        effort=int(payload["effort"]),
        token_cost=int(payload["token_cost"]),
        monetary_cost=float(payload["monetary_cost"]),
        reversibility=float(payload["reversibility"]),
        information_gain=float(payload["information_gain"]),
        risk=_risk(dict(payload.get("risk", {}))),
        requires_approval=bool(payload.get("requires_approval", False)),
    )


def evaluate_strategic_selection_benchmark(path: str | Path) -> BenchmarkResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    version = str(payload.get("version", ""))
    cases = payload.get("cases")
    if not version or not isinstance(cases, list) or not cases:
        raise ValueError("benchmark requires a version and at least one case")

    failures: list[str] = []
    for case in cases:
        case_id = str(case.get("id", "unnamed"))
        actions = tuple(_action(item) for item in case.get("actions", []))
        budgets = dict(case.get("budgets", {}))
        decision = select_strategic_action(actions, **budgets)
        expected = (case.get("expected_status"), case.get("expected_action_id"))
        actual = (decision.status, decision.recommended_action_id)
        if actual != expected:
            failures.append(f"{case_id}: expected {expected!r}, got {actual!r}")

    return BenchmarkResult(
        version=version,
        passed=not failures,
        passed_cases=len(cases) - len(failures),
        total_cases=len(cases),
        failures=tuple(failures),
    )
