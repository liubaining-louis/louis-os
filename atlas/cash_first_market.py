"""Cash-first portfolio routing for universal internet opportunities.

This module prioritizes fast, evidence-backed missions over headline prize size.
Effort and page volume reduce a mission's score but never reject it on their own:
a high-quality first-win candidate can receive a documented scope exception.
The module also turns real last-mile account, terms, identity and payout gates into
precise human-action notifications without stopping autonomous preparation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping


CASH_FIRST_MAX_EFFORT_HOURS = 3.0
SCOPE_EXCEPTION_MIN_SCORE = 55.0


_DEFAULT_EFFORT_HOURS = {
    "microservice": 4.0,
    "user_research": 2.0,
    "freelance": 8.0,
    "freelance_marketplace": 8.0,
    "code_bounty": 8.0,
    "security_bounty": 12.0,
    "data_competition": 40.0,
    "challenge_prize": 120.0,
    "public_procurement": 160.0,
    "direct_commercial_lead": 12.0,
}

_GATE_ACTIONS = {
    "account_required": "Authorize or use an existing lawful account for the platform.",
    "terms_acceptance_required": "Review and accept the platform or opportunity terms.",
    "legal_entity_required": "Confirm the eligible legal entity that will submit and receive payment.",
    "identity_or_kyc_required": "Complete the required identity or KYC verification with truthful information.",
    "payout_setup_required": "Choose and configure one lawful payout method supported by the payer.",
    "signature_required": "Review and sign the required document or contract.",
    "tax_information_required": "Provide the truthful tax information required for payout.",
}


@dataclass(frozen=True)
class CashAssessment:
    opportunity_id: str
    title: str
    source_url: str
    lane: str
    cash_priority_score: float
    estimated_effort_hours: float
    scope_exception_applied: bool
    estimated_hourly_value: float
    reward_amount: float
    currency: str
    time_to_cash_days: int
    payment_methods: tuple[str, ...]
    decision_status: str
    human_gate_required: bool
    ready_for_human_action: bool
    human_actions: tuple[str, ...]
    urgency: str
    risk_summary: str
    prepared_artifacts: tuple[str, ...]
    rationale: tuple[str, ...]
    evidence: tuple[str, ...]
    deadline: str = ""

    @property
    def notification_fingerprint(self) -> str:
        raw = "|".join((self.opportunity_id, self.decision_status, *self.human_actions))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def estimate_effort_hours(opportunity: Mapping[str, Any]) -> float:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    explicit = _float(metadata.get("estimated_effort_hours"), 0.0)
    if explicit > 0:
        return min(explicit, 10_000.0)
    category = str(opportunity.get("source_category") or "")
    return _DEFAULT_EFFORT_HOURS.get(category, 24.0)


def accepted_payment_methods(opportunity: Mapping[str, Any]) -> tuple[str, ...]:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    methods = metadata.get("payment_methods")
    if isinstance(methods, (list, tuple)):
        cleaned = tuple(dict.fromkeys(str(item).strip() for item in methods if str(item).strip()))
        if cleaned:
            return cleaned
    return ("payer-supported lawful method to be confirmed",)


def _cash_score(opportunity: Mapping[str, Any], effort: float) -> float:
    reward = max(0.0, _float(opportunity.get("reward_amount")))
    time_to_cash = max(0, _int(opportunity.get("time_to_cash_days"), 30))
    accessibility = min(1.0, max(0.0, _float(opportunity.get("accessibility"), 0.0)))
    competition = min(1.0, max(0.0, _float(opportunity.get("competition"), 0.5)))
    risk = min(1.0, max(0.0, _float(opportunity.get("risk"), 0.5)))
    cost = min(1.0, max(0.0, _float(opportunity.get("cost"), 0.5)))
    human_dependency = min(1.0, max(0.0, _float(opportunity.get("human_dependency"), 0.5)))

    speed = 1.0 / (1.0 + time_to_cash / 14.0)
    small_scope = 1.0 / (1.0 + effort / 8.0)
    payment_probability = accessibility * (1.0 - competition) * (1.0 - risk)
    hourly_value = reward / max(effort, 0.5)
    hourly_quality = min(1.0, hourly_value / 100.0)

    score = 100.0 * (
        speed * 0.25
        + small_scope * 0.25
        + payment_probability * 0.25
        + (1.0 - cost) * 0.10
        + (1.0 - human_dependency) * 0.05
        + hourly_quality * 0.10
    )
    if bool(opportunity.get("reward_verified")):
        score += 5.0
    return round(max(0.0, min(100.0, score)), 2)


def _human_actions(opportunity: Mapping[str, Any], decision: Mapping[str, Any]) -> tuple[str, ...]:
    blockers = [str(item) for item in decision.get("blockers") or []]
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    for flag, blocker in (
        ("payout_setup_required", "payout_setup_required"),
        ("signature_required", "signature_required"),
        ("tax_information_required", "tax_information_required"),
    ):
        if bool(metadata.get(flag)) and blocker not in blockers:
            blockers.append(blocker)

    exact = metadata.get("human_action_instructions")
    if bool(metadata.get("submission_dossier_prepared")) and isinstance(exact, (list, tuple)):
        cleaned = tuple(dict.fromkeys(str(item).strip() for item in exact if str(item).strip()))
        if cleaned:
            return cleaned
    return tuple(_GATE_ACTIONS[item] for item in blockers if item in _GATE_ACTIONS)


def assess_cash_priority(opportunity: Mapping[str, Any]) -> CashAssessment:
    decision = opportunity.get("decision") if isinstance(opportunity.get("decision"), Mapping) else {}
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    effort = estimate_effort_hours(opportunity)
    reward = max(0.0, _float(opportunity.get("reward_amount")))
    score = _cash_score(opportunity, effort)
    time_to_cash = max(0, _int(opportunity.get("time_to_cash_days"), 30))
    cost = min(1.0, max(0.0, _float(opportunity.get("cost"), 0.5)))
    competition = min(1.0, max(0.0, _float(opportunity.get("competition"), 0.5)))
    accessibility = min(1.0, max(0.0, _float(opportunity.get("accessibility"), 0.0)))
    risk = min(1.0, max(0.0, _float(opportunity.get("risk"), 0.5)))
    verified = bool(opportunity.get("reward_verified"))
    decision_status = str(decision.get("status") or "rejected")
    missing_capabilities = tuple(str(item) for item in decision.get("missing_capabilities") or [])

    is_small = effort <= CASH_FIRST_MAX_EFFORT_HOURS
    is_fast = time_to_cash <= 30
    low_friction = cost <= 0.25 and competition <= 0.65 and accessibility >= 0.50
    scope_exception_applied = (
        not is_small
        and is_fast
        and low_friction
        and score >= SCOPE_EXCEPTION_MIN_SCORE
        and not missing_capabilities
        and decision_status in {"prepare_then_gate", "executable_now"}
    )
    if decision_status == "rejected" or not verified:
        lane = "rejected"
    elif (is_small and is_fast and low_friction) or scope_exception_applied:
        lane = "cash_first"
    else:
        lane = "strategic"

    actions = _human_actions(opportunity, decision)
    dossier_required = bool(metadata.get("submission_dossier_required"))
    dossier_prepared = bool(metadata.get("submission_dossier_prepared"))
    ready_for_human_action = (
        lane == "cash_first"
        and bool(actions)
        and not missing_capabilities
        and decision_status in {"prepare_then_gate", "executable_now"}
        and (not dossier_required or dossier_prepared)
    )
    urgency = "high" if ready_for_human_action and lane == "cash_first" else "normal"
    if ready_for_human_action and str(opportunity.get("deadline") or "").strip():
        urgency = "high"

    prepared_artifacts = tuple(
        str(metadata.get(name) or "").strip()
        for name in ("proposal_path", "proposal_manifest_path")
        if str(metadata.get(name) or "").strip()
    )
    risk_summary = (
        f"risk={risk:.2f}; platform account and terms gate only; "
        "KYC, payout and contract actions remain deferred until explicitly required"
    )
    rationale = (
        f"estimated_effort_hours={effort:g}",
        f"time_to_cash_days={time_to_cash}",
        f"competition={competition:.2f}",
        f"cost={cost:.2f}",
        f"accessibility={accessibility:.2f}",
        f"scope_exception_applied={str(scope_exception_applied).lower()}",
        "hours and page volume are scoring inputs, not standalone rejection gates",
        "headline prize size is not used as the primary ranking signal",
    )
    evidence = tuple(
        dict.fromkeys(
            str(item)
            for item in (opportunity.get("payment_evidence") or []) + (opportunity.get("evidence") or [])
            if str(item).strip()
        )
    )
    return CashAssessment(
        opportunity_id=str(opportunity.get("opportunity_id") or ""),
        title=str(opportunity.get("title") or ""),
        source_url=str(opportunity.get("source_url") or ""),
        lane=lane,
        cash_priority_score=score,
        estimated_effort_hours=effort,
        scope_exception_applied=scope_exception_applied,
        estimated_hourly_value=round(reward / max(effort, 0.5), 2),
        reward_amount=reward,
        currency=str(opportunity.get("currency") or "unknown"),
        time_to_cash_days=time_to_cash,
        payment_methods=accepted_payment_methods(opportunity),
        decision_status=decision_status,
        human_gate_required=bool(actions),
        ready_for_human_action=ready_for_human_action,
        human_actions=actions,
        urgency=urgency,
        risk_summary=risk_summary,
        prepared_artifacts=prepared_artifacts,
        rationale=rationale,
        evidence=evidence,
        deadline=str(opportunity.get("deadline") or ""),
    )


def build_cash_first_portfolio(market_payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = market_payload.get("opportunities") if isinstance(market_payload, Mapping) else []
    assessments = [assess_cash_priority(row) for row in rows if isinstance(row, Mapping)]
    assessments.sort(key=lambda item: (-item.cash_priority_score, item.opportunity_id))
    cash_first = [item for item in assessments if item.lane == "cash_first"]
    strategic = [item for item in assessments if item.lane == "strategic"]
    human_actions = [item for item in assessments if item.ready_for_human_action]
    return {
        "schema_version": "1.0",
        "generated_at": str(market_payload.get("generated_at") or ""),
        "policy": {
            "primary_lane": "cash_first",
            "cash_first_preferred_effort_hours": CASH_FIRST_MAX_EFFORT_HOURS,
            "scope_exception_minimum_score": SCOPE_EXCEPTION_MIN_SCORE,
            "effort_and_page_policy": (
                "soft scoring factors only; a verified, feasible, fast, low-friction mission may exceed them"
            ),
            "strategic_capacity_share_maximum": 0.20,
            "payment_method_policy": "accept any lawful payer-supported method; request truthful setup only at the exact gate",
            "human_validation_policy": "prepare autonomously, then request the smallest concrete human action",
        },
        "counts": {
            "cash_first": len(cash_first),
            "strategic": len(strategic),
            "rejected": sum(item.lane == "rejected" for item in assessments),
            "human_action_ready": len(human_actions),
        },
        "top_cash_first": asdict(cash_first[0]) | {"notification_fingerprint": cash_first[0].notification_fingerprint}
        if cash_first
        else None,
        "cash_first": [asdict(item) | {"notification_fingerprint": item.notification_fingerprint} for item in cash_first],
        "strategic": [asdict(item) | {"notification_fingerprint": item.notification_fingerprint} for item in strategic],
        "human_action_ready": [
            asdict(item) | {"notification_fingerprint": item.notification_fingerprint} for item in human_actions
        ],
    }


def human_action_payload(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    items = portfolio.get("human_action_ready") if isinstance(portfolio, Mapping) else []
    items = [item for item in items if isinstance(item, Mapping)]
    return {
        "schema_version": "1.0",
        "generated_at": str(portfolio.get("generated_at") or ""),
        "status": "action_required" if items else "none",
        "count": len(items),
        "items": items,
        "instruction": (
            "Notify the owner with the exact action, payout, deadline, risk, prepared artifacts and evidence; continue all reversible work meanwhile."
            if items
            else "Do not notify the owner; continue scouting payable missions."
        ),
    }


def prioritize_capability_backlog(backlog: Mapping[str, Any], portfolio: Mapping[str, Any]) -> dict[str, Any]:
    lane_by_id: dict[str, str] = {}
    for lane in ("cash_first", "strategic"):
        for item in portfolio.get(lane) or []:
            if isinstance(item, Mapping):
                lane_by_id[str(item.get("opportunity_id") or "")] = lane

    enriched: list[dict[str, Any]] = []
    for raw in backlog.get("items") or []:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        origin_ids = [str(value) for value in item.get("originating_opportunity_ids") or []]
        lane = "cash_first" if any(lane_by_id.get(value) == "cash_first" for value in origin_ids) else "strategic"
        item["execution_priority"] = lane
        item["deferred_by_cash_first"] = lane != "cash_first"
        issue = item.get("issue")
        if isinstance(issue, Mapping):
            issue_copy = dict(issue)
            prefix = "[Cash-first] " if lane == "cash_first" else "[Strategic deferred] "
            title = str(issue_copy.get("title") or "")
            if not title.startswith("["):
                issue_copy["title"] = prefix + title
            issue_copy["body"] = (
                str(issue_copy.get("body") or "")
                + f"\n\n## Portfolio lane\n`{lane}` — strategic work is limited while the first verified payment remains zero.\n"
            )
            item["issue"] = issue_copy
        enriched.append(item)
    enriched.sort(
        key=lambda item: (
            item.get("execution_priority") != "cash_first",
            -_float(item.get("priority_score")),
            str(item.get("capability_id") or ""),
        )
    )
    result = dict(backlog)
    result["items"] = enriched
    result["cash_first_count"] = sum(item.get("execution_priority") == "cash_first" for item in enriched)
    result["strategic_deferred_count"] = sum(item.get("execution_priority") == "strategic" for item in enriched)
    result["policy"] = "create cash-first capability tasks before strategic tasks"
    return result
