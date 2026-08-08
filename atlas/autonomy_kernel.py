from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MARKET_REFRESH_COOLDOWN_CYCLES = 120
MARKET_EXPANSION_ACTIONS = frozenset({
    "execute_opportunity_factory_query_pack",
    "activate_next_small_mission_source",
    "activate_next_authorized_official_source",
    "search_validated_software_micro_missions",
})


@dataclass(frozen=True)
class AutonomousDecision:
    decision_id: str
    created_at: str
    action: str
    authority: str
    score: float
    observation: dict[str, Any]
    hypothesis: str
    expected_effect: str
    confidence: float
    estimated_cost: float
    reversibility: str
    success_criteria: list[str]
    rollback: str
    review_after_cycles: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _decision_cycle(value: Any) -> int | None:
    parts = str(value or "").split("-", 2)
    if len(parts) != 3 or parts[0] != "autonomy":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _last_action_cycle(learning: Any, action_name: str) -> int | None:
    if not isinstance(learning, Mapping):
        return None
    actions = learning.get("actions")
    if not isinstance(actions, Mapping):
        return None
    action = actions.get(action_name)
    if not isinstance(action, Mapping):
        return None
    return _decision_cycle(action.get("last_decision_id"))


def build_state(results: Path) -> dict[str, Any]:
    money = _load(results / "monetization.json", {})
    market = _load(results / "universal_market_cycle.json", {})
    candidates_payload = _load(results / "monetization_candidates.json", {})
    review = _load(results / "multi_model_monetization.json", {})
    crypto = _load(results / "crypto_realization.json", {})
    previous = _load(results / "autonomy_state.json", {})
    last = _load(results / "autonomy_last_decision.json", {})
    learning = _load(results / "autonomy_learning.json", {})

    candidates = candidates_payload.get("candidates") if isinstance(candidates_payload, Mapping) else []
    candidates = candidates if isinstance(candidates, list) else []
    opportunities = _safe_int(market.get("opportunities_observed"))
    executable = _safe_int(market.get("opportunities_executable_now", money.get("universal_market_executable_now")))
    prepare = _safe_int(market.get("opportunities_prepare_then_gate", money.get("universal_market_prepare_then_gate")))
    submissions = _safe_int(money.get("external_submissions_verified", money.get("external_actions_submitted")))
    revenue = _safe_float(money.get("revenue_confirmed_eur", money.get("revenue_verified_eur")))
    cycle = _safe_int(previous.get("cycle")) + 1
    last_delta = last.get("measured_delta") if isinstance(last.get("measured_delta"), Mapping) else {}
    last_effect = sum(abs(_safe_float(value)) for value in last_delta.values())
    last_market_refresh_cycle = _last_action_cycle(learning, "market_refresh")
    market_refresh_age_cycles = (
        None
        if last_market_refresh_cycle is None
        else max(0, cycle - last_market_refresh_cycle)
    )

    return {
        "schema_version": "1.0",
        "updated_at": _now(),
        "cycle": cycle,
        "opportunities_observed": opportunities,
        "candidates": len(candidates),
        "executable_now": executable,
        "prepare_then_gate": prepare,
        "external_submissions_verified": submissions,
        "revenue_verified": revenue,
        "crypto_received": bool(crypto.get("crypto_received")),
        "crypto_stage": crypto.get("stage"),
        "multi_model_status": review.get("status"),
        "multi_model_recommendation": review.get("recommendation"),
        "multi_model_selected_candidate": review.get("selected_candidate_id"),
        "primary_blocker": money.get("primary_blocker"),
        "market_next_action": market.get("next_action"),
        "last_market_refresh_cycle": last_market_refresh_cycle,
        "market_refresh_age_cycles": market_refresh_age_cycles,
        "market_refresh_cooldown_cycles": MARKET_REFRESH_COOLDOWN_CYCLES,
        "last_autonomous_action": last.get("action"),
        "last_autonomous_action_effect": last_effect,
    }


def _candidate_actions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    opportunities = _safe_int(state.get("opportunities_observed"))
    candidates = _safe_int(state.get("candidates"))
    executable = _safe_int(state.get("executable_now"))
    prepare = _safe_int(state.get("prepare_then_gate"))
    recommendation = str(state.get("multi_model_recommendation") or "")
    market_next_action = str(state.get("market_next_action") or "")
    market_refresh_age = (
        None
        if state.get("market_refresh_age_cycles") is None
        else _safe_int(state.get("market_refresh_age_cycles"))
    )
    market_refresh_due = (
        market_next_action in MARKET_EXPANSION_ACTIONS
        and (
            market_refresh_age is None
            or market_refresh_age >= MARKET_REFRESH_COOLDOWN_CYCLES
        )
    )

    if executable > 0 or recommendation == "execute_now":
        actions.append({
            "action": "execution_attempt",
            "score": 0.98,
            "hypothesis": "At least one currently qualified opportunity can progress toward a verified submission.",
            "expected_effect": "Increase BUILDING/SUBMITTED while preserving evidence gates.",
            "confidence": 0.82,
            "estimated_cost": 0.30,
            "success": ["deterministic executor produces a verified submission receipt or a causal blocker"],
        })

    market_score = 0.99 if market_refresh_due else 0.92 if opportunities == 0 else 0.78 if opportunities < 5 else 0.45
    if candidates == 0 and not market_refresh_due:
        market_score += 0.06
    actions.append({
        "action": "market_refresh",
        "score": min(market_score, 0.99),
        "hypothesis": (
            "The persisted market plan explicitly requests a cash-first source expansion that has not run within the bounded cooldown."
            if market_refresh_due
            else "Refreshing and widening observed market state will increase qualified opportunity density."
        ),
        "expected_effect": "Increase opportunities_observed and/or executable candidates.",
        "confidence": 0.78,
        "estimated_cost": 0.12,
        "success": ["fresh market state is produced", "opportunity coverage does not regress without recorded cause"],
    })

    if candidates == 0 or (executable == 0 and prepare == 0):
        actions.append({
            "action": "candidate_recovery",
            "score": 0.88 if candidates == 0 else 0.69,
            "hypothesis": "Candidate state is stale, incomplete or poorly bridged to validated capabilities.",
            "expected_effect": "Recover/normalize candidates and reduce false zero-candidate states.",
            "confidence": 0.74,
            "estimated_cost": 0.10,
            "success": ["candidate registry is validated or exact recovery failure is recorded"],
        })

    if candidates > 0 and recommendation not in {"execute_now", "prepare_then_gate"}:
        actions.append({
            "action": "quality_review",
            "score": 0.73,
            "hypothesis": "The current candidate set needs fresh multi-model ranking and acceptance analysis.",
            "expected_effect": "Produce a current execute/prepare/reject recommendation for the best candidate.",
            "confidence": 0.72,
            "estimated_cost": 0.22,
            "success": ["multi-model review completes or records provider failure"],
        })

    return actions


def choose_next_action(state: Mapping[str, Any]) -> AutonomousDecision:
    actions = _candidate_actions(state)
    last_action = str(state.get("last_autonomous_action") or "")
    last_effect = _safe_float(state.get("last_autonomous_action_effect"))
    for item in actions:
        # Impact-confidence score with a modest cost penalty. A repeated action that
        # produced no measurable state change is automatically demoted for one cycle.
        utility = float(item["score"]) * float(item["confidence"]) - 0.15 * float(item["estimated_cost"])
        if item["action"] == last_action and last_effect == 0.0:
            utility -= 0.22
        item["utility"] = utility
    selected = max(actions, key=lambda item: (item["utility"], item["score"]))
    cycle = _safe_int(state.get("cycle"))
    return AutonomousDecision(
        decision_id=f"autonomy-{cycle:08d}-{selected['action']}",
        created_at=_now(),
        action=str(selected["action"]),
        authority="GREEN",
        score=round(float(selected["utility"]), 4),
        observation=dict(state),
        hypothesis=str(selected["hypothesis"]),
        expected_effect=str(selected["expected_effect"]),
        confidence=float(selected["confidence"]),
        estimated_cost=float(selected["estimated_cost"]),
        reversibility="high",
        success_criteria=list(selected["success"]),
        rollback="Return to previous persisted state; do not widen security/payment authority.",
        review_after_cycles=1,
    )


def update_learning(results: Path, decision: AutonomousDecision, outcome: Mapping[str, Any]) -> dict[str, Any]:
    path = results / "autonomy_learning.json"
    learning = _load(path, {"schema_version": "1.0", "actions": {}, "last_updated_at": None})
    if not isinstance(learning, dict):
        learning = {"schema_version": "1.0", "actions": {}}
    actions = learning.setdefault("actions", {})
    action = actions.setdefault(decision.action, {"attempts": 0, "successes": 0, "failures": 0, "effective": 0, "last_outcome": None})
    action["attempts"] = _safe_int(action.get("attempts")) + 1
    success = str(outcome.get("status") or "") in {"completed", "ok", "success"}
    if success:
        action["successes"] = _safe_int(action.get("successes")) + 1
    else:
        action["failures"] = _safe_int(action.get("failures")) + 1
    delta = outcome.get("measured_delta") if isinstance(outcome.get("measured_delta"), Mapping) else {}
    if any(abs(_safe_float(value)) > 0 for value in delta.values()):
        action["effective"] = _safe_int(action.get("effective")) + 1
    action["last_outcome"] = dict(outcome)
    action["last_decision_id"] = decision.decision_id
    action["updated_at"] = _now()
    learning["last_updated_at"] = _now()
    path.write_text(json.dumps(learning, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return learning
