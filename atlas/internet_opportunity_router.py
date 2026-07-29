"""Adaptive multidomain Internet opportunity routing for Louis OS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

DOMAIN_KEYWORDS = {
    "code_automation": {"python", "api", "automation", "script", "webhook", "bug", "integration"},
    "data_csv": {"csv", "excel", "spreadsheet", "data cleaning", "deduplicate", "reconcile"},
    "b2b_research": {"research", "supplier", "competitor", "market", "lead list", "sourcing"},
    "writing_documentation": {"documentation", "technical writing", "procedure", "article", "rewrite"},
    "web_landing_pages": {"landing page", "frontend", "form", "netlify", "deployment", "responsive"},
    "translation": {"translation", "translate", "french", "english", "chinese"},
    "open_source_bounties": {"bounty", "github issue", "open source", "sponsored issue"},
    "digital_products": {"template", "digital product", "dataset", "report", "notion template"},
}

@dataclass(frozen=True)
class RoutedOpportunity:
    domain: str
    lane: str
    decision: str
    score: float
    reasons: tuple[str, ...]


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k, "")) for k in ("title", "description", "skills", "category")).casefold()


def infer_domain(item: dict[str, Any]) -> tuple[str, float]:
    text = _text(item)
    ranked: list[tuple[float, str]] = []
    for domain, words in DOMAIN_KEYWORDS.items():
        hits = sum(1 for word in words if word in text)
        ranked.append((hits / max(1, len(words)), domain))
    fit, domain = max(ranked)
    return domain, min(1.0, fit * 3.0)


def route(item: dict[str, Any]) -> RoutedOpportunity:
    reasons: list[str] = []
    domain, inferred_fit = infer_domain(item)
    fit = float(item.get("capability_fit", inferred_fit))
    effort = float(item.get("effort_hours", 999))
    human_actions = int(item.get("human_actions_required", 0))

    if item.get("charcoal_related"):
        reasons.append("charcoal_excluded")
    if item.get("fresh_open_verified") is not True:
        reasons.append("status_not_freshly_verified_open")
    if not item.get("payment_path"):
        reasons.append("payment_path_missing")
    if not item.get("acceptance_criteria"):
        reasons.append("acceptance_criteria_missing")
    if item.get("legal_policy_pass") is not True:
        reasons.append("legal_or_platform_policy_not_verified")
    if item.get("personal_eligibility_required"):
        reasons.append("personal_eligibility_required")
    if item.get("active_competing_claim"):
        reasons.append("active_competing_claim")

    if reasons:
        decision = "reject"
    elif fit >= 0.70 and effort <= 8 and human_actions == 0:
        decision = "execute_now"
    elif fit >= 0.70 and effort <= 8 and human_actions <= 1:
        decision = "prepare_then_gate"
    elif item.get("market_signal_verified") and effort <= 16:
        decision = "capability_build"
    else:
        decision = "reject"
        reasons.append("insufficient_capability_or_economics")

    lane = "exploit" if fit >= 0.85 else "adjacent" if fit >= 0.55 else "experimental"
    reward = max(0.0, float(item.get("reward_eur", 0)))
    payment_confidence = max(0.0, min(1.0, float(item.get("payment_confidence", 0))))
    competition = max(0.0, min(1.0, float(item.get("competition_risk", 0.5))))
    score = 0.0
    if decision in {"execute_now", "prepare_then_gate"}:
        score = reward * fit * payment_confidence * (1 - 0.6 * competition) / max(1.0, effort)
    elif decision == "capability_build":
        score = 0.1 * reward * max(fit, 0.1) / max(1.0, effort)

    return RoutedOpportunity(domain, lane, decision, round(score, 3), tuple(reasons))


def route_all(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items:
        routed = route(item)
        enriched = dict(item)
        enriched["internet_opportunity_router"] = {
            "domain": routed.domain,
            "lane": routed.lane,
            "decision": routed.decision,
            "score": routed.score,
            "reasons": list(routed.reasons),
            "forecast_only_not_pipeline_or_revenue": True,
        }
        output.append(enriched)
    priority = {"execute_now": 3, "prepare_then_gate": 2, "capability_build": 1, "reject": 0}
    return sorted(
        output,
        key=lambda row: (
            priority[row["internet_opportunity_router"]["decision"]],
            row["internet_opportunity_router"]["score"],
        ),
        reverse=True,
    )


def next_pivot(metrics: dict[str, Any]) -> str:
    if int(metrics.get("verified_payments", 0)) > 0:
        return "expand_similar_searches"
    if int(metrics.get("proposals_without_reply", 0)) >= 5:
        return "change_offer_or_message"
    if int(metrics.get("replies_without_conversion", 0)) >= 3:
        return "change_scope_price_or_acceptance_terms"
    if int(metrics.get("source_results_without_eligible", 0)) >= 50:
        return "pause_source_and_replace"
    if int(metrics.get("rejected_without_candidate", 0)) >= 30:
        return "regenerate_queries_and_shift_domain"
    return "continue_measured_search"
