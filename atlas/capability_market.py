"""Market-backed capability planning for the cash-first monetization loop.

The engine groups similar paid opportunities, scores the reusable capability that
would unlock them, and produces conservative simulations. Simulations are planning
evidence only: they never count as pipeline, submission, conversion or revenue.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import math
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


_AI_PROHIBITED_TERMS = (
    "no ai",
    "no artificial intelligence",
    "do not use ai",
    "without ai",
    "ai tools are prohibited",
    "ai-generated wording is acceptable",  # handled with negation guard below
    "ai-generated wording is not acceptable",
    "no ai-generated",
    "human-written only",
    "human written only",
    "must be written by a human",
)

_DEFAULT_EFFORT = {
    "freelance_marketplace": 8.0,
    "microservice": 4.0,
    "user_research": 2.0,
    "code_bounty": 8.0,
    "security_bounty": 12.0,
    "challenge_prize": 120.0,
    "data_competition": 40.0,
    "public_procurement": 160.0,
}

_IMPLEMENTATION_COST = {
    "validated": 0.05,
    "experimental": 0.35,
    "unavailable": 0.85,
    "forbidden": 1.0,
    "unknown": 0.55,
}


@dataclass(frozen=True)
class MissionCluster:
    cluster_id: str
    capability_id: str
    capability_status: str
    deliverable_family: str
    lane: str
    opportunity_count: int
    source_count: int
    source_ids: tuple[str, ...]
    opportunity_ids: tuple[str, ...]
    verified_value_by_currency: Mapping[str, float]
    capped_score_value: float
    median_reward: float
    median_effort_hours: float
    median_time_to_cash_days: float
    median_competition: float
    median_accessibility: float
    first_payment_probability: float
    reusable_deliverable_ratio: float
    implementation_cost: float
    capability_market_score: float
    top_opportunity_url: str
    top_opportunity_title: str
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityPlan:
    rank: int
    capability_id: str
    cluster_id: str
    capability_market_score: float
    lane: str
    opportunity_count: int
    source_count: int
    objective: str
    required_interface: Mapping[str, str]
    acceptance_tests: tuple[str, ...]
    fixture_opportunity_ids: tuple[str, ...]
    promotion_rule: str
    stop_rule: str
    budget_rule: str
    immediate_next_action: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def estimated_effort(opportunity: Mapping[str, Any]) -> float:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    explicit = _number(metadata.get("estimated_effort_hours"), 0.0)
    if explicit > 0:
        return min(explicit, 10_000.0)
    return _DEFAULT_EFFORT.get(str(opportunity.get("source_category") or ""), 24.0)


def explicitly_prohibits_ai(opportunity: Mapping[str, Any]) -> bool:
    pieces: list[str] = [
        str(opportunity.get("title") or ""),
        str(opportunity.get("description") or ""),
    ]
    pieces.extend(str(item) for item in opportunity.get("payment_evidence") or [])
    text = "\n".join(pieces).casefold()
    if "ai-generated wording is acceptable" in text and "not acceptable" not in text:
        text = text.replace("ai-generated wording is acceptable", "")
    return any(term in text for term in _AI_PROHIBITED_TERMS if term != "ai-generated wording is acceptable")


def reject_ai_prohibited_opportunities(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    rejected = 0
    for raw in rows:
        item = dict(raw)
        if explicitly_prohibits_ai(item):
            decision = dict(item.get("decision") or {})
            blockers = [str(value) for value in decision.get("blockers") or []]
            if "automation_prohibited_by_payer" not in blockers:
                blockers.append("automation_prohibited_by_payer")
            decision.update(
                {
                    "status": "rejected",
                    "blockers": blockers,
                    "missing_capabilities": [],
                    "next_action": "reject_and_continue_discovery",
                    "human_action_minimal": "none",
                    "evidence": list(dict.fromkeys([*decision.get("evidence", []), *item.get("evidence", [])])),
                }
            )
            metadata = dict(item.get("metadata") or {})
            metadata["policy_rejection"] = "automation_prohibited_by_payer"
            metadata["policy_rejection_verified"] = True
            item["decision"] = decision
            item["metadata"] = metadata
            rejected += 1
        output.append(item)
    return output, rejected


def _lane(opportunity: Mapping[str, Any]) -> str:
    decision = opportunity.get("decision") if isinstance(opportunity.get("decision"), Mapping) else {}
    if str(decision.get("status") or "") == "rejected" or not bool(opportunity.get("reward_verified")):
        return "rejected"
    effort = estimated_effort(opportunity)
    time_to_cash = _integer(opportunity.get("time_to_cash_days"), 30)
    competition = _number(opportunity.get("competition"), 0.5)
    cost = _number(opportunity.get("cost"), 0.5)
    accessibility = _number(opportunity.get("accessibility"), 0.0)
    if effort <= 16 and time_to_cash <= 30 and competition <= 0.65 and cost <= 0.25 and accessibility >= 0.50:
        return "cash_first"
    return "strategic"


def _capability_ids(opportunity: Mapping[str, Any]) -> tuple[str, ...]:
    values = tuple(str(item).strip() for item in opportunity.get("required_capabilities") or [] if str(item).strip())
    return values or ("unclassified_delivery",)


def _family(opportunity: Mapping[str, Any], capability_id: str) -> str:
    text = f"{opportunity.get('title', '')}\n{opportunity.get('description', '')}".casefold()
    if capability_id == "evidence_research_dossier":
        if any(term in text for term in ("lead", "contact list", "prospect", "company list")):
            return "lead_qualification_and_sourced_lists"
        return "web_research_and_evidence_dossier"
    if capability_id == "python_data_analysis":
        return "spreadsheet_cleanup_and_data_validation"
    if capability_id == "translation_delivery":
        return "bounded_translation"
    if capability_id == "structured_document_delivery":
        if any(term in text for term in ("proofread", "editing", "memoir", "rewrite")):
            return "proofreading_and_document_editing"
        return "structured_document_delivery"
    if capability_id in {"deterministic_text_replacement", "broken_link_replacement"}:
        return "narrow_repository_correction"
    if capability_id == "simple_test_expectation_replacement":
        return "narrow_test_correction"
    if capability_id == "configuration_scalar_replacement":
        return "configuration_correction"
    if capability_id == "technical_proposal":
        return "technical_proposal"
    return capability_id


def _cluster_id(lane: str, capability_id: str, family: str) -> str:
    raw = f"{lane}|{capability_id}|{family}"
    return "cluster-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _probability(opportunities: Sequence[Mapping[str, Any]]) -> float:
    values: list[float] = []
    for item in opportunities:
        accessibility = min(1.0, max(0.0, _number(item.get("accessibility"), 0.0)))
        competition = min(1.0, max(0.0, _number(item.get("competition"), 0.5)))
        risk = min(1.0, max(0.0, _number(item.get("risk"), 0.5)))
        delay = max(0, _integer(item.get("time_to_cash_days"), 30))
        speed = 1.0 / (1.0 + delay / 21.0)
        values.append(accessibility * (1.0 - competition) * (1.0 - risk) * speed)
    return round(min(1.0, max(0.0, median(values) if values else 0.0)), 4)


def cluster_opportunities(
    rows: Sequence[Mapping[str, Any]],
    capability_statuses: Mapping[str, str],
) -> list[MissionCluster]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for item in rows:
        lane = _lane(item)
        if lane == "rejected":
            continue
        for capability_id in _capability_ids(item):
            grouped[(lane, capability_id, _family(item, capability_id))].append(item)

    clusters: list[MissionCluster] = []
    for (lane, capability_id, family), opportunities in grouped.items():
        rewards = [max(0.0, _number(item.get("reward_amount"))) for item in opportunities]
        efforts = [estimated_effort(item) for item in opportunities]
        delays = [max(0, _integer(item.get("time_to_cash_days"), 30)) for item in opportunities]
        competitions = [min(1.0, max(0.0, _number(item.get("competition"), 0.5))) for item in opportunities]
        accessibilities = [min(1.0, max(0.0, _number(item.get("accessibility"), 0.0))) for item in opportunities]
        source_ids = tuple(sorted({str(item.get("source_id") or "unknown") for item in opportunities}))
        opportunity_ids = tuple(sorted(str(item.get("opportunity_id") or "") for item in opportunities))
        currency_values: dict[str, float] = defaultdict(float)
        for item, reward in zip(opportunities, rewards, strict=True):
            currency_values[str(item.get("currency") or "unknown")] += reward

        status = str(capability_statuses.get(capability_id) or "unknown")
        implementation_cost = _IMPLEMENTATION_COST.get(status, _IMPLEMENTATION_COST["unknown"])
        probability = _probability(opportunities)
        cash_share = 1.0 if lane == "cash_first" else 0.0
        volume = min(1.0, math.log1p(len(opportunities)) / math.log(11.0))
        diversity = min(1.0, len(source_ids) / 3.0)
        speed = 1.0 / (1.0 + median(delays) / 21.0)
        small_scope = 1.0 / (1.0 + median(efforts) / 8.0)
        reuse = min(1.0, 0.55 + 0.12 * max(0, len(opportunities) - 1) + 0.08 * max(0, len(source_ids) - 1))
        raw_score = 100.0 * (
            0.26 * cash_share
            + 0.18 * volume
            + 0.24 * probability
            + 0.10 * speed
            + 0.10 * small_scope
            + 0.07 * reuse
            + 0.05 * diversity
        )
        score = round(max(0.0, min(100.0, raw_score * (1.0 - 0.35 * implementation_cost))), 2)
        top = max(
            opportunities,
            key=lambda item: (
                _number(item.get("accessibility"), 0.0) * (1.0 - _number(item.get("competition"), 0.5)),
                -estimated_effort(item),
                _number(item.get("reward_amount"), 0.0),
            ),
        )
        clusters.append(
            MissionCluster(
                cluster_id=_cluster_id(lane, capability_id, family),
                capability_id=capability_id,
                capability_status=status,
                deliverable_family=family,
                lane=lane,
                opportunity_count=len(opportunities),
                source_count=len(source_ids),
                source_ids=source_ids,
                opportunity_ids=opportunity_ids,
                verified_value_by_currency=dict(sorted(currency_values.items())),
                capped_score_value=round(sum(min(value, 1_000.0) for value in rewards), 2),
                median_reward=round(median(rewards), 2),
                median_effort_hours=round(median(efforts), 2),
                median_time_to_cash_days=round(median(delays), 2),
                median_competition=round(median(competitions), 4),
                median_accessibility=round(median(accessibilities), 4),
                first_payment_probability=probability,
                reusable_deliverable_ratio=round(reuse, 4),
                implementation_cost=implementation_cost,
                capability_market_score=score,
                top_opportunity_url=str(top.get("source_url") or ""),
                top_opportunity_title=str(top.get("title") or ""),
                rationale=(
                    f"lane={lane}",
                    f"opportunities={len(opportunities)}",
                    f"sources={len(source_ids)}",
                    f"median_effort_hours={median(efforts):g}",
                    f"median_time_to_cash_days={median(delays):g}",
                    f"first_payment_probability={probability:.4f}",
                    f"capability_status={status}",
                    "headline rewards are capped for scoring and strategic prizes cannot dominate cash-first rank",
                ),
            )
        )
    clusters.sort(
        key=lambda item: (
            item.lane != "cash_first",
            -item.capability_market_score,
            -item.opportunity_count,
            item.capability_id,
            item.deliverable_family,
        )
    )
    return clusters


def simulate_cluster_revenue(cluster: MissionCluster, opportunities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [item for item in opportunities if str(item.get("opportunity_id") or "") in cluster.opportunity_ids]
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in selected:
        grouped[str(item.get("currency") or "unknown")].append(max(0.0, _number(item.get("reward_amount"))))
    scenarios: dict[str, dict[str, float]] = {}
    for currency, rewards in sorted(grouped.items()):
        middle = median(rewards)
        count = len(rewards)
        scenarios[currency] = {
            "conservative_expected_value": round(count * 0.05 * middle, 2),
            "base_expected_value": round(count * 0.12 * middle, 2),
            "upside_expected_value": round(count * 0.25 * middle, 2),
            "observed_opportunity_count": count,
            "median_verified_reward": round(middle, 2),
        }
    return {
        "cluster_id": cluster.cluster_id,
        "capability_id": cluster.capability_id,
        "type": "simulation_only",
        "scope": "currently observed qualified opportunities; not annualized",
        "scenarios_by_currency": scenarios,
        "annualization_status": "insufficient_history",
        "counted_as_pipeline": False,
        "counted_as_revenue": False,
    }


def build_capability_plans(clusters: Sequence[MissionCluster], maximum: int = 5) -> list[CapabilityPlan]:
    eligible = [
        cluster
        for cluster in clusters
        if cluster.lane == "cash_first" and cluster.capability_status not in {"validated", "forbidden", "unavailable"}
    ]
    plans: list[CapabilityPlan] = []
    for rank, cluster in enumerate(eligible[:maximum], start=1):
        family = cluster.deliverable_family
        plans.append(
            CapabilityPlan(
                rank=rank,
                capability_id=cluster.capability_id,
                cluster_id=cluster.cluster_id,
                capability_market_score=cluster.capability_market_score,
                lane=cluster.lane,
                opportunity_count=cluster.opportunity_count,
                source_count=cluster.source_count,
                objective=(
                    f"Implement and validate `{cluster.capability_id}` as a reusable `{family}` delivery capability "
                    f"for {cluster.opportunity_count} currently observed cash-first opportunity(ies)."
                ),
                required_interface={
                    "input": "canonical opportunity dossier, source materials, acceptance criteria and payment evidence",
                    "output": "bounded deliverable, validation report, hashes and execution receipt",
                },
                acceptance_tests=(
                    "reject missing or unverified payer and scope evidence",
                    "reject work that prohibits AI, automation or the authorized delivery method",
                    "produce a deterministic or bounded artifact from a fixture",
                    "validate completeness, schema, formatting and source traceability",
                    "record artifact hashes, test command, result and elapsed effort",
                    "fail closed at account, terms, identity, contract and payout gates",
                    "re-run market qualification immediately after promotion",
                ),
                fixture_opportunity_ids=cluster.opportunity_ids[:3],
                promotion_rule="Promote only after green unit tests, one reproducible dry-run artifact and no regression in the versioned business benchmark.",
                stop_rule="Defer if the cluster has no qualifying mission for three consecutive cycles, score falls below 35, or a mandatory human/physical constraint dominates.",
                budget_rule="Use existing local and cloud infrastructure first; any paid dependency or external purchase requires explicit approval.",
                immediate_next_action=f"create_or_update_capability_issue:{cluster.capability_id}",
                evidence=tuple(value for value in (cluster.top_opportunity_url, *cluster.source_ids) if value),
            )
        )
    return plans


def enrich_capability_backlog(
    backlog: Mapping[str, Any],
    clusters: Sequence[MissionCluster],
    plans: Sequence[CapabilityPlan],
) -> dict[str, Any]:
    best_by_capability: dict[str, MissionCluster] = {}
    for cluster in clusters:
        existing = best_by_capability.get(cluster.capability_id)
        if existing is None or cluster.capability_market_score > existing.capability_market_score:
            best_by_capability[cluster.capability_id] = cluster
    rank_by_capability = {plan.capability_id: plan.rank for plan in plans}

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in backlog.get("items") or []:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        capability_id = str(item.get("capability_id") or "")
        seen.add(capability_id)
        cluster = best_by_capability.get(capability_id)
        if cluster:
            item.update(
                {
                    "capability_market_score": cluster.capability_market_score,
                    "market_cluster_id": cluster.cluster_id,
                    "market_opportunity_count": cluster.opportunity_count,
                    "market_source_count": cluster.source_count,
                    "market_lane": cluster.lane,
                    "first_payment_probability": cluster.first_payment_probability,
                    "median_effort_hours": cluster.median_effort_hours,
                    "median_time_to_cash_days": cluster.median_time_to_cash_days,
                    "capability_market_rank": rank_by_capability.get(capability_id),
                }
            )
        items.append(item)

    for plan in plans:
        if plan.capability_id in seen:
            continue
        cluster = best_by_capability[plan.capability_id]
        marker = f"<!-- louis-capability-market:{plan.capability_id} -->"
        items.append(
            {
                "capability_id": plan.capability_id,
                "marker": marker,
                "execution_priority": "cash_first",
                "deferred_by_cash_first": False,
                "priority_score": plan.capability_market_score,
                "market_value": cluster.capped_score_value,
                "originating_opportunity_ids": list(cluster.opportunity_ids),
                "capability_market_score": plan.capability_market_score,
                "market_cluster_id": plan.cluster_id,
                "market_opportunity_count": plan.opportunity_count,
                "market_source_count": plan.source_count,
                "market_lane": plan.lane,
                "first_payment_probability": cluster.first_payment_probability,
                "median_effort_hours": cluster.median_effort_hours,
                "median_time_to_cash_days": cluster.median_time_to_cash_days,
                "capability_market_rank": plan.rank,
                "specification": {
                    "objective": plan.objective,
                    "required_interface": dict(plan.required_interface),
                    "acceptance_tests": list(plan.acceptance_tests),
                    "promotion_rule": plan.promotion_rule,
                    "stop_rule": plan.stop_rule,
                    "budget_rule": plan.budget_rule,
                    "retry_action": "Re-run capability market scoring and universal qualification immediately after promotion.",
                    "originating_market_url": cluster.top_opportunity_url,
                },
                "issue": {
                    "marker": marker,
                    "title": f"[Cash-first market rank {plan.rank}] Capability gap: {plan.capability_id}",
                    "body": "\n".join(
                        [
                            marker,
                            "## Capability-market objective",
                            plan.objective,
                            "",
                            f"- Market score: {plan.capability_market_score}",
                            f"- Cluster: `{plan.cluster_id}`",
                            f"- Current opportunities unlocked: {plan.opportunity_count}",
                            f"- Independent sources: {plan.source_count}",
                            f"- First-payment probability signal: {cluster.first_payment_probability}",
                            f"- Evidence: {cluster.top_opportunity_url}",
                            "",
                            "## Acceptance tests",
                            *[f"- [ ] {test}" for test in plan.acceptance_tests],
                            "",
                            "## Promotion, stop and budget rules",
                            f"- {plan.promotion_rule}",
                            f"- {plan.stop_rule}",
                            f"- {plan.budget_rule}",
                            "",
                            "Simulation values are planning signals only and are not revenue, pipeline or submissions.",
                        ]
                    ),
                },
            }
        )

    items.sort(
        key=lambda item: (
            item.get("market_lane") != "cash_first",
            item.get("capability_market_rank") is None,
            item.get("capability_market_rank") or 9999,
            -_number(item.get("capability_market_score"), _number(item.get("priority_score"))),
            str(item.get("capability_id") or ""),
        )
    )
    result = dict(backlog)
    result["items"] = items
    result["count"] = len(items)
    result["capability_market_engine"] = "active"
    result["capability_market_plan_count"] = len(plans)
    result["capability_market_policy"] = "rank reusable cash-first capability coverage before strategic prize size"
    return result


def market_payload(
    clusters: Sequence[MissionCluster],
    plans: Sequence[CapabilityPlan],
    rejected_ai_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "primary_objective": "first verified payment",
            "cash_first_effort_hours_max": 16,
            "cash_first_time_to_cash_days_max": 30,
            "strategic_capacity_share_maximum": 0.20,
            "simulation_truth_rule": "simulations never count as pipeline, submissions, conversions or revenue",
        },
        "counts": {
            "clusters": len(clusters),
            "cash_first_clusters": sum(cluster.lane == "cash_first" for cluster in clusters),
            "strategic_clusters": sum(cluster.lane == "strategic" for cluster in clusters),
            "capability_build_plans": len(plans),
            "ai_prohibited_opportunities_rejected": rejected_ai_count,
        },
        "top_cluster": clusters[0].to_dict() if clusters else None,
        "clusters": [cluster.to_dict() for cluster in clusters],
        "capability_build_plans": [plan.to_dict() for plan in plans],
    }
