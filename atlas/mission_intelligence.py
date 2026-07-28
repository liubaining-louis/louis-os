"""Evidence-bound Mission Intelligence Engine.

The module ranks payable missions, learns source/capability yield from verified
lifecycle events, allocates discovery effort and detects economic stagnation.
It never performs external actions and never treats forecasts as revenue.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import log1p
from typing import Any, Iterable, Mapping

TERMINAL_STAGES = {"lost", "closed", "expired", "paid"}
STAGE_ORDER = {
    "observed": 0,
    "qualified": 1,
    "prepared": 2,
    "submitted": 3,
    "viewed": 4,
    "replied": 5,
    "negotiated": 6,
    "won": 7,
    "delivered": 8,
    "accepted": 9,
    "paid": 10,
    "lost": 10,
    "closed": 10,
    "expired": 10,
}


@dataclass(frozen=True)
class IntelligencePolicy:
    max_effort_hours: float = 16.0
    max_time_to_cash_days: int = 30
    max_human_actions: int = 2
    exploration_share: float = 0.10
    adjacent_share: float = 0.20
    proven_share: float = 0.70
    stagnation_observed_without_prepared: int = 50
    stagnation_prepared_without_submitted: int = 10
    stagnation_submitted_without_reply: int = 5
    stagnation_days_without_progress: int = 14


@dataclass(frozen=True)
class MissionScore:
    opportunity_id: str
    expected_value_eur: float
    expected_value_per_hour_eur: float
    payment_probability: float
    response_probability: float
    win_probability: float
    explanation: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "expected_value_eur": round(self.expected_value_eur, 2),
            "expected_value_per_hour_eur": round(self.expected_value_per_hour_eur, 2),
            "payment_probability": round(self.payment_probability, 4),
            "response_probability": round(self.response_probability, 4),
            "win_probability": round(self.win_probability, 4),
            "explanation": list(self.explanation),
            "forecast_only_not_pipeline_or_revenue": True,
        }


def _clamp(value: float, lower: float = 0.01, upper: float = 0.95) -> float:
    return max(lower, min(upper, value))


def _rate(successes: int, attempts: int, *, prior_success: float, prior_total: float) -> float:
    return (successes + prior_success) / (attempts + prior_total)


def build_outcome_metrics(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate only explicit lifecycle events.

    Each event should contain opportunity_id, stage and optional source_id,
    capability_id, proposal_variant, verified_revenue_eur and evidence.
    """
    per_opportunity: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    capability_counts: dict[str, Counter[str]] = defaultdict(Counter)
    variant_counts: dict[str, Counter[str]] = defaultdict(Counter)
    verified_revenue = 0.0

    for raw in events:
        opportunity_id = str(raw.get("opportunity_id") or "").strip()
        stage = str(raw.get("stage") or "").strip()
        if not opportunity_id or stage not in STAGE_ORDER:
            continue
        evidence = raw.get("evidence")
        if stage in {"submitted", "viewed", "replied", "won", "delivered", "accepted", "paid"} and not evidence:
            continue
        prior = per_opportunity.get(opportunity_id)
        if prior is None or STAGE_ORDER[stage] >= STAGE_ORDER[str(prior["stage"])]:
            per_opportunity[opportunity_id] = dict(raw)

    for item in per_opportunity.values():
        stage = str(item["stage"])
        source = str(item.get("source_id") or "unknown")
        capability = str(item.get("capability_id") or "unknown")
        variant = str(item.get("proposal_variant") or "unknown")
        for bucket, key in ((source_counts, source), (capability_counts, capability), (variant_counts, variant)):
            bucket[key]["observed"] += 1
            for marker in ("prepared", "submitted", "replied", "won", "paid"):
                if STAGE_ORDER[stage] >= STAGE_ORDER[marker] and stage not in {"lost", "closed", "expired"}:
                    bucket[key][marker] += 1
        if stage == "paid":
            verified_revenue += max(0.0, float(item.get("verified_revenue_eur") or 0.0))

    def summarize(rows: Mapping[str, Counter[str]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, count in rows.items():
            submitted = count["submitted"]
            replied = count["replied"]
            won = count["won"]
            paid = count["paid"]
            output[key] = {
                **dict(count),
                "response_rate": round(_rate(replied, submitted, prior_success=1.0, prior_total=4.0), 4),
                "win_rate": round(_rate(won, max(replied, submitted), prior_success=0.5, prior_total=5.0), 4),
                "payment_rate": round(_rate(paid, max(won, submitted), prior_success=1.0, prior_total=8.0), 4),
            }
        return output

    return {
        "opportunities_with_latest_stage": len(per_opportunity),
        "verified_revenue_eur": round(verified_revenue, 2),
        "by_source": summarize(source_counts),
        "by_capability": summarize(capability_counts),
        "by_proposal_variant": summarize(variant_counts),
    }


def score_mission(
    opportunity: Mapping[str, Any],
    metrics: Mapping[str, Any],
    policy: IntelligencePolicy = IntelligencePolicy(),
) -> MissionScore | None:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), Mapping) else {}
    effort = float(metadata.get("estimated_effort_hours") or opportunity.get("estimated_effort_hours") or 8.0)
    cash_days = int(metadata.get("time_to_cash_days") or opportunity.get("time_to_cash_days") or 30)
    human_actions = int(metadata.get("human_action_count") or len(metadata.get("human_action_instructions") or []))
    reward = float(opportunity.get("reward_amount_eur") or opportunity.get("reward_amount") or 0.0)
    if reward <= 0 or effort <= 0 or effort > policy.max_effort_hours or cash_days > policy.max_time_to_cash_days:
        return None
    if human_actions > policy.max_human_actions:
        return None

    source_id = str(opportunity.get("source_id") or "unknown")
    capabilities = [str(value) for value in opportunity.get("required_capabilities") or ["unknown"]]
    source_stats = (metrics.get("by_source") or {}).get(source_id, {})
    cap_rows = [(metrics.get("by_capability") or {}).get(capability, {}) for capability in capabilities]

    response = float(source_stats.get("response_rate") or 0.20)
    win = float(source_stats.get("win_rate") or 0.10)
    payment = float(source_stats.get("payment_rate") or 0.20)
    if cap_rows:
        response = (response + sum(float(row.get("response_rate") or 0.20) for row in cap_rows) / len(cap_rows)) / 2
        win = (win + sum(float(row.get("win_rate") or 0.10) for row in cap_rows) / len(cap_rows)) / 2
        payment = (payment + sum(float(row.get("payment_rate") or 0.20) for row in cap_rows) / len(cap_rows)) / 2

    explanation: list[str] = []
    bids = metadata.get("bid_count")
    if bids is not None:
        bid_count = max(0, int(bids))
        competition_factor = 1.0 / (1.0 + log1p(bid_count) / 3.0)
        win *= competition_factor
        explanation.append(f"competition_factor={competition_factor:.3f} from {bid_count} bids")
    clarity = float(metadata.get("scope_clarity") or 0.5)
    proof_fit = float(metadata.get("validated_product_fit") or 0.0)
    client_quality = float(metadata.get("client_quality") or 0.5)
    freshness = float(metadata.get("freshness_score") or 0.5)
    response *= 0.65 + 0.35 * freshness
    win *= 0.55 + 0.20 * clarity + 0.25 * proof_fit
    payment *= 0.65 + 0.35 * client_quality
    payment *= max(0.6, 1.0 - 0.12 * human_actions)

    response = _clamp(response)
    win = _clamp(win)
    payment = _clamp(payment)
    total_probability = response * win * payment
    risk_cost = float(metadata.get("risk_cost_eur") or 0.0)
    platform_cost = float(metadata.get("platform_cost_eur") or 0.0)
    expected_value = max(0.0, reward * total_probability - risk_cost - platform_cost)
    expected_per_hour = expected_value / effort
    explanation.extend(
        [
            f"response_probability={response:.3f}",
            f"win_probability={win:.3f}",
            f"payment_probability={payment:.3f}",
            f"validated_product_fit={proof_fit:.2f}",
            f"scope_clarity={clarity:.2f}",
            f"human_actions={human_actions}",
            f"effort_hours={effort:g}",
        ]
    )
    return MissionScore(
        opportunity_id=str(opportunity.get("opportunity_id") or ""),
        expected_value_eur=expected_value,
        expected_value_per_hour_eur=expected_per_hour,
        payment_probability=payment,
        response_probability=response,
        win_probability=win,
        explanation=tuple(explanation),
    )


def allocate_search(metrics: Mapping[str, Any], policy: IntelligencePolicy = IntelligencePolicy()) -> dict[str, float]:
    sources = metrics.get("by_source") or {}
    proven = [key for key, row in sources.items() if int(row.get("paid") or 0) > 0 or int(row.get("won") or 0) > 0]
    adjacent = [key for key, row in sources.items() if key not in proven and int(row.get("prepared") or 0) > 0]
    allocation = {
        "proven_sources": policy.proven_share if proven else 0.0,
        "adjacent_sources": policy.adjacent_share if adjacent else 0.0,
        "experimental_sources": policy.exploration_share,
    }
    unused = 1.0 - sum(allocation.values())
    if unused > 0:
        allocation["experimental_sources"] += unused
    return {key: round(value, 4) for key, value in allocation.items()}


def detect_stagnation(events: Iterable[Mapping[str, Any]], days_without_progress: int, policy: IntelligencePolicy = IntelligencePolicy()) -> list[dict[str, str]]:
    counts = Counter(str(item.get("stage") or "") for item in events)
    actions: list[dict[str, str]] = []
    if counts["observed"] >= policy.stagnation_observed_without_prepared and counts["prepared"] == 0:
        actions.append({"trigger": "discovery_without_preparation", "action": "change sources and search for validated-product matches"})
    if counts["prepared"] >= policy.stagnation_prepared_without_submitted and counts["submitted"] == 0:
        actions.append({"trigger": "preparation_without_submission", "action": "resolve the smallest account gate and freeze new dossier creation"})
    if counts["submitted"] >= policy.stagnation_submitted_without_reply and counts["replied"] == 0:
        actions.append({"trigger": "submissions_without_reply", "action": "test a materially different proposal variant, offer and price"})
    if days_without_progress >= policy.stagnation_days_without_progress:
        actions.append({"trigger": "time_without_economic_progress", "action": "pivot source, category or product lane and preserve the prior lane as a control"})
    return actions
