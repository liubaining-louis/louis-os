"""Hard-gated selection for Louis OS's first externally verified paid mission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class Decision:
    eligible: bool
    reasons: tuple[str, ...]
    score: float
    recommended_offer: str | None


OFFER_KEYWORDS = {
    "csv_rescue": {"csv", "excel", "spreadsheet", "deduplicate", "data cleaning", "normalize"},
    "api_connection_fix": {"api", "webhook", "integration", "endpoint", "oauth", "json"},
    "landing_page_repair": {"landing page", "responsive", "form", "frontend", "deployment", "netlify"},
    "research_brief": {"research", "market", "competitor", "supplier", "brief", "analysis"},
}


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k, "")) for k in ("title", "description", "skills", "category")).lower()


def infer_offer(item: dict[str, Any]) -> tuple[str | None, float]:
    text = _text(item)
    ranked = []
    for offer, words in OFFER_KEYWORDS.items():
        hits = sum(1 for word in words if word in text)
        ranked.append((hits / max(1, len(words)), offer))
    fit, offer = max(ranked)
    return (offer if fit > 0 else None, round(min(1.0, fit * 2.5), 3))


def evaluate(item: dict[str, Any]) -> Decision:
    reasons: list[str] = []
    offer, inferred_fit = infer_offer(item)
    fit = float(item.get("capability_fit", inferred_fit))
    effort = float(item.get("effort_hours", 999))

    if item.get("fresh_open_verified") is not True:
        reasons.append("status_not_freshly_verified_open")
    if not item.get("payment_path"):
        reasons.append("payment_path_missing")
    if not item.get("acceptance_criteria"):
        reasons.append("acceptance_criteria_missing")
    if effort > 8:
        reasons.append("effort_above_first_mission_limit")
    if fit < 0.70:
        reasons.append("capability_fit_below_0_70")
    if item.get("personal_eligibility_required"):
        reasons.append("personal_eligibility_required")
    if item.get("active_competing_claim"):
        reasons.append("active_competing_claim")
    if item.get("legal_policy_pass") is not True:
        reasons.append("legal_or_platform_policy_not_verified")
    if int(item.get("human_actions_required", 0)) > 1:
        reasons.append("too_many_human_actions")

    eligible = not reasons
    reward = max(0.0, float(item.get("reward_eur", 0)))
    payment_confidence = max(0.0, min(1.0, float(item.get("payment_confidence", 0))))
    competition = max(0.0, min(1.0, float(item.get("competition_risk", 0.5))))
    score = 0.0
    if eligible:
        score = (reward * fit * payment_confidence * (1.0 - 0.6 * competition)) / max(1.0, effort)
    return Decision(eligible, tuple(reasons), round(score, 3), offer)


def rank(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in items:
        decision = evaluate(item)
        enriched = dict(item)
        enriched["first_paid_mission"] = {
            "eligible": decision.eligible,
            "reasons": list(decision.reasons),
            "score": decision.score,
            "recommended_offer": decision.recommended_offer,
            "forecast_only_not_submission_or_revenue": True,
        }
        output.append(enriched)
    return sorted(output, key=lambda x: x["first_paid_mission"]["score"], reverse=True)
