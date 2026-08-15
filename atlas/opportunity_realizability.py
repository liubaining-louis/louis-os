"""Fail-closed cash-realizability gate for monetization opportunities.

This layer answers a different question from attractiveness or technical readiness:
can an advertised reward plausibly become withdrawable cash under Louis OS's current
identity, authorization, competition and payout constraints?
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config" / "monetization_source_risk_registry.json"

_AI_PROHIBITED_RE = re.compile(
    r"\b(?:human contributors? only|humans? only|no ai|ai (?:generated|assisted|agents?) (?:are )?(?:not allowed|prohibited|ineligible)|automated submissions? (?:are )?(?:not allowed|prohibited))\b",
    re.I,
)
_BROKEN_PAYOUT_RE = re.compile(
    r"\b(?:cannot withdraw|can't withdraw|withdrawal (?:is )?(?:broken|failing|unavailable)|payout (?:is )?(?:broken|failing|unavailable)|claim callback.{0,40}404)\b",
    re.I | re.S,
)

_HUMAN_GATE_PREREQUISITES = {
    "third_party_account_required",
    "identity_or_eligibility_check_required",
    "external_terms_or_contract_required",
    "payment_or_fee_required",
}


@dataclass(frozen=True)
class OpportunityRealizability:
    decision: str
    cash_realizability_score: float
    hard_reasons: tuple[str, ...]
    human_gate_reasons: tuple[str, ...]
    soft_reasons: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def executable(self) -> bool:
        return self.decision in {"execute", "downrank"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_source_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_REGISTRY
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"providers": {}}
    return data if isinstance(data, dict) else {"providers": {}}


def _provider_policy(provider: str, registry: Mapping[str, Any]) -> Mapping[str, Any]:
    providers = registry.get("providers", {}) if isinstance(registry, Mapping) else {}
    policy = providers.get(provider, {}) if isinstance(providers, Mapping) else {}
    return policy if isinstance(policy, Mapping) else {}


def _bool(item: Mapping[str, Any], name: str, fallback: bool | None = None) -> bool | None:
    value = item.get(name, fallback)
    return value if isinstance(value, bool) else fallback


def assess_opportunity_realizability(
    item: Mapping[str, Any],
    *,
    provider: str = "github_public_issue",
    readiness_prerequisites: Iterable[str] = (),
    source_truth_verified: bool = True,
    registry: Mapping[str, Any] | None = None,
) -> OpportunityRealizability:
    registry = registry or load_source_registry()
    policy = _provider_policy(provider, registry)
    title = str(item.get("title", ""))
    body = str(item.get("body", ""))
    text = f"{title}\n{body}"

    hard: list[str] = []
    human: list[str] = []
    soft: list[str] = []
    evidence: list[str] = []

    official_state_open = _bool(item, "official_state_open", str(item.get("state", "open")).lower() == "open")
    ai_allowed = _bool(item, "ai_allowed", policy.get("ai_allowed") if isinstance(policy.get("ai_allowed"), bool) else None)
    eligible = _bool(item, "eligible", True)
    assigned_to_other = _bool(item, "assigned_to_other", None)
    if assigned_to_other is None:
        assignee = item.get("assignee")
        assignees = item.get("assignees") or []
        assigned_to_other = bool(assignee or assignees)

    payout_healthy = _bool(
        item,
        "payout_withdrawal_healthy",
        policy.get("payout_withdrawal_healthy") if isinstance(policy.get("payout_withdrawal_healthy"), bool) else None,
    )
    payout_method_verified = _bool(
        item,
        "payout_method_verified",
        policy.get("payout_method_verified") if isinstance(policy.get("payout_method_verified"), bool) else None,
    )
    currency_liquid = _bool(
        item,
        "currency_liquidity_verified",
        policy.get("currency_liquidity_verified") if isinstance(policy.get("currency_liquidity_verified"), bool) else None,
    )
    submit_route_verified = _bool(item, "external_submit_route_verified", None)

    if not source_truth_verified:
        hard.append("official_source_truth_not_verified")
    if official_state_open is False:
        hard.append("official_source_closed_or_stale")
    if ai_allowed is False or _AI_PROHIBITED_RE.search(text):
        hard.append("ai_or_automation_ineligible")
        m = _AI_PROHIBITED_RE.search(text)
        if m:
            evidence.append(m.group(0)[:160])
    if eligible is False:
        hard.append("eligibility_failed")
    if assigned_to_other:
        hard.append("assigned_to_other_contributor")
    if payout_healthy is False or _BROKEN_PAYOUT_RE.search(text):
        hard.append("payout_or_withdrawal_not_reliably_realizable")
        m = _BROKEN_PAYOUT_RE.search(text)
        if m:
            evidence.append(m.group(0)[:160])

    prereqs = set(readiness_prerequisites)
    for gate in sorted(prereqs & _HUMAN_GATE_PREREQUISITES):
        human.append(gate)
    if _bool(item, "requires_signed_registration", bool(policy.get("requires_signed_registration"))):
        human.append("signed_registration_or_new_identity_required")
    if _bool(item, "requires_terms_acceptance", bool(policy.get("requires_terms_acceptance"))):
        human.append("terms_acceptance_required")
    if _bool(item, "requires_kyc", False):
        human.append("kyc_required")
    if _bool(item, "requires_captcha", False):
        human.append("captcha_required")
    if _bool(item, "requires_stake_or_spend", False):
        human.append("stake_or_spend_required")

    try:
        competitors = max(0, int(item.get("active_competitor_count") or item.get("comments") or 0))
    except (TypeError, ValueError):
        competitors = 0
    try:
        prs = max(0, int(item.get("existing_pr_count") or 0))
    except (TypeError, ValueError):
        prs = 0

    score = float(policy.get("baseline_score", 55.0) or 55.0)
    if payout_method_verified is not True:
        score -= 18.0
        soft.append("payout_method_not_yet_independently_verified")
    if currency_liquid is False:
        score -= 12.0
        soft.append("reward_currency_liquidity_not_verified")
    elif currency_liquid is None:
        score -= 5.0
        soft.append("reward_currency_liquidity_unknown")
    if submit_route_verified is False:
        score -= 18.0
        soft.append("external_submission_route_not_verified")
    elif submit_route_verified is None:
        score -= 6.0
        soft.append("external_submission_route_unknown")
    if competitors:
        score -= min(35.0, competitors * 1.5)
        soft.append(f"active_competition={competitors}")
    if prs:
        score -= min(30.0, prs * 10.0)
        soft.append(f"existing_prs={prs}")

    default_decision = str(policy.get("default_decision", "downrank"))
    if hard or default_decision == "reject":
        decision = "reject"
        score = min(score, 5.0)
    elif human or default_decision == "human_gate":
        decision = "human_gate"
        score = min(score, 55.0)
    elif default_decision == "passive":
        decision = "passive"
        score = min(score, 50.0)
    else:
        decision = "execute" if score >= 65.0 else "downrank"

    return OpportunityRealizability(
        decision=decision,
        cash_realizability_score=round(max(0.0, min(score, 100.0)), 1),
        hard_reasons=tuple(dict.fromkeys(hard)),
        human_gate_reasons=tuple(dict.fromkeys(human)),
        soft_reasons=tuple(dict.fromkeys(soft)),
        evidence=tuple(dict.fromkeys(evidence)),
    )


def candidate_is_cash_executable(candidate: Mapping[str, Any], minimum_score: float = 45.0) -> bool:
    return (
        candidate.get("cash_realizability_decision") in {"execute", "downrank"}
        and float(candidate.get("cash_realizability_score", 0.0) or 0.0) >= minimum_score
    )
