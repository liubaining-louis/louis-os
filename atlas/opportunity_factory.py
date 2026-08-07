"""Opportunity Factory: turn a narrow marketplace scout into a broad, measurable market search plan.

This module does not scrape or submit anything itself. It diagnoses funnel bottlenecks,
expands the executable capability vocabulary, allocates search across independent market
lanes, and distinguishes BAD candidates from UNKNOWN candidates that require verification.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence

TARGET_ALLOCATION = {
    "explicit_marketplaces": 0.30,
    "public_requests": 0.20,
    "proactive_problem_discovery": 0.35,
    "capability_experiments": 0.15,
}

MICRO_CAPABILITIES = (
    "csv_cleanup", "csv_deduplication", "excel_merge", "excel_formula_fix",
    "spreadsheet_normalization", "json_conversion", "xml_conversion", "python_script",
    "python_file_automation", "api_debug", "webhook_fix", "html_css_fix",
    "responsive_fix", "landing_page", "static_website", "wordpress_css_fix",
    "wordpress_content_update", "broken_link_fix", "contact_form_fix", "github_actions_fix",
    "unit_test_creation", "readme_creation", "technical_documentation", "deployment_fix",
    "netlify_deployment", "public_web_research", "competitor_research", "product_comparison",
    "lead_research_public_business_data", "technical_summary", "proofreading_en",
    "proofreading_fr", "translation_fr_en", "translation_en_fr", "email_copywriting",
    "product_description", "markdown_cleanup", "data_format_cleanup", "simple_report_generation",
    "website_issue_audit",
)

QUERY_FAMILIES = {
    "explicit_marketplaces": (
        "small fixed price {capability} task budget",
        "urgent {capability} freelance project",
        "quick {capability} help fixed price",
    ),
    "public_requests": (
        "need help with {capability}",
        "looking for someone to {capability}",
        "paid help {capability}",
    ),
    "proactive_problem_discovery": (
        "business website broken contact form",
        "small business website mobile layout issue",
        "company website broken links outdated page",
        "public spreadsheet manual process automation opportunity",
    ),
    "capability_experiments": (
        "small paid {capability} request",
    ),
}

UNKNOWN_REASONS = {
    "fresh_open_status", "buyer_intent", "verified_payment", "acceptance_criteria",
    "status_not_freshly_verified_open", "payment_evidence_missing", "acceptance_criteria_missing",
}

HARD_REJECT_REASONS = {
    "platform_policy_blocked", "geographically_ineligible", "physically_inaccessible",
    "commercial_offer_not_job", "already_completed", "already_assigned", "expired_or_closed",
    "economically_unviable", "hourly_rate_below_cash_first_floor", "ai_prohibited",
}


@dataclass(frozen=True)
class FunnelDiagnosis:
    stage: str
    severity: str
    reason: str
    corrective_action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def classify_rejection(reason: str) -> str:
    reason = str(reason or "").strip()
    if reason in HARD_REJECT_REASONS:
        return "bad"
    if reason in UNKNOWN_REASONS or any(token in reason for token in ("missing", "unverified", "unknown")):
        return "unknown"
    return "review"


def diagnose_funnel(metrics: Mapping[str, Any]) -> list[FunnelDiagnosis]:
    signals = int(metrics.get("signals_seen", metrics.get("scout_items_inspected", 0)) or 0)
    observed = int(metrics.get("opportunities_observed", metrics.get("universal_market_opportunities_observed", 0)) or 0)
    dossiers = int(metrics.get("dossiers_prepared", metrics.get("simple_mission_dossiers_prepared", 0)) or 0)
    submitted = int(metrics.get("external_submissions_verified", metrics.get("external_actions_submitted", 0)) or 0)
    replies = int(metrics.get("qualified_replies", 0) or 0)
    wins = int(metrics.get("conversions", 0) or 0)
    revenue = float(metrics.get("revenue_confirmed_eur", metrics.get("revenue_received", 0)) or 0)

    issues: list[FunnelDiagnosis] = []
    if signals < 1000 or observed < 50:
        issues.append(FunnelDiagnosis(
            "discovery", "critical",
            f"market perception is too small: signals={signals}, opportunities={observed}",
            "increase breadth and target at least 1000 signals and 50 normalized opportunities per cycle",
        ))
    if observed >= 20 and dossiers == 0:
        issues.append(FunnelDiagnosis(
            "qualification_capability", "high",
            f"opportunities exist but none become dossiers: observed={observed}",
            "separate unknown from bad and match against the expanded micro-capability registry",
        ))
    if dossiers >= 3 and submitted == 0:
        issues.append(FunnelDiagnosis(
            "execution", "critical",
            f"prepared work is not crossing the external boundary: dossiers={dossiers}",
            "repair and activate the receipt-backed submission executor",
        ))
    if submitted >= 5 and replies == 0:
        issues.append(FunnelDiagnosis(
            "commercial_message", "high",
            f"submissions receive no replies: submitted={submitted}",
            "test price, proof artifact and proposal framing one variable at a time",
        ))
    if replies >= 3 and wins == 0:
        issues.append(FunnelDiagnosis(
            "conversion", "high",
            f"replies are not converting: replies={replies}",
            "tighten scope, price and proof of delivery",
        ))
    if wins > 0 and revenue <= 0:
        issues.append(FunnelDiagnosis(
            "collection", "critical",
            "won work has not produced verified cash",
            "instrument acceptance, invoice/milestone and payment receipt transitions",
        ))
    return issues


def allocation_plan(current: Mapping[str, float] | None = None) -> dict[str, Any]:
    current = current or {}
    return {
        "target": TARGET_ALLOCATION,
        "current": {key: float(current.get(key, 0.0) or 0.0) for key in TARGET_ALLOCATION},
        "delta": {key: round(TARGET_ALLOCATION[key] - float(current.get(key, 0.0) or 0.0), 4) for key in TARGET_ALLOCATION},
        "rule": "never allocate 100% to a single lane; preserve exploitation, adjacent discovery and bounded experiments",
    }


def capability_registry(existing: Sequence[str] | None = None) -> dict[str, Any]:
    existing_set = {str(x) for x in (existing or [])}
    missing = [cap for cap in MICRO_CAPABILITIES if cap not in existing_set]
    return {
        "target_count": len(MICRO_CAPABILITIES),
        "existing_count": len(existing_set.intersection(MICRO_CAPABILITIES)),
        "missing": missing,
        "all": list(MICRO_CAPABILITIES),
        "promotion_rule": "capability may become executable only after deterministic demo/test evidence exists",
    }


def build_query_pack(capabilities: Sequence[str] | None = None, maximum: int = 120) -> list[dict[str, str]]:
    capabilities = tuple(capabilities or MICRO_CAPABILITIES)
    rows: list[dict[str, str]] = []
    for lane, templates in QUERY_FAMILIES.items():
        if lane == "proactive_problem_discovery":
            for template in templates:
                rows.append({"lane": lane, "capability": "problem_detection", "query": template})
            continue
        for capability in capabilities:
            for template in templates:
                rows.append({"lane": lane, "capability": capability, "query": template.format(capability=capability.replace("_", " "))})
                if len(rows) >= maximum:
                    return rows
    return rows[:maximum]


def build_factory_plan(
    monetization: Mapping[str, Any],
    *,
    existing_capabilities: Sequence[str] | None = None,
    current_allocation: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    diagnoses = diagnose_funnel(monetization)
    registry = capability_registry(existing_capabilities)
    query_pack = build_query_pack(registry["all"])
    return {
        "schema_version": "1.0",
        "objective": "find payable problems across the open internet and convert them into verified external actions",
        "funnel_diagnosis": [item.to_dict() for item in diagnoses],
        "allocation": allocation_plan(current_allocation),
        "capability_registry": registry,
        "query_pack": query_pack,
        "cycle_targets": {
            "signals_seen_min": 1000,
            "normalized_opportunities_min": 50,
            "deep_verifications_min": 20,
            "capability_matches_min": 5,
            "dossiers_target": 2,
            "verified_external_actions_target_when_valid_candidate_exists": 1,
        },
        "candidate_semantics": {
            "bad": "terminal reject",
            "unknown": "verification queue, not terminal reject",
            "review": "manual or higher-order decision intelligence review",
        },
        "economic_floor": {
            "minimum_hourly_value": 8.0,
            "currency_reference": "EUR-equivalent",
            "rule": "candidates below floor cannot rank as top cash-first opportunity",
        },
        "truth": {
            "external_submissions_verified": int(monetization.get("external_submissions_verified", monetization.get("external_actions_submitted", 0)) or 0),
            "revenue_verified_eur": float(monetization.get("revenue_confirmed_eur", 0) or 0),
            "plan_is_not_submission": True,
        },
    }
