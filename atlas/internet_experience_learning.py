"""Evidence-weighted learning from public Internet observations and verified outcomes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import exp
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


AUTHORITATIVE_DOMAINS = {
    "github.com", "docs.github.com", "europa.eu", "service-public.fr", "legifrance.gouv.fr",
    "data.gouv.fr", "insee.fr", "who.int", "oecd.org",
}


@dataclass(frozen=True)
class InternetObservation:
    observation_id: str
    claim_key: str
    claim: str
    source_url: str
    observed_at: str
    evidence_type: str = "public_web"
    independent_group: str = ""
    primary_source: bool = False
    published_at: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OutcomeFeedback:
    claim_key: str
    outcome: str
    success: bool
    observed_at: str
    receipt: str | None = None


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def source_reliability(observation: InternetObservation) -> float:
    domain = _domain(observation.source_url)
    score = 0.45
    if observation.primary_source:
        score += 0.30
    if domain in AUTHORITATIVE_DOMAINS or domain.endswith(".gov") or domain.endswith(".gouv.fr"):
        score += 0.20
    if observation.evidence_type in {"official_document", "payer_listing", "external_receipt"}:
        score += 0.15
    if not observation.source_url.startswith("https://"):
        score -= 0.20
    return round(max(0.05, min(0.98, score)), 4)


def freshness_weight(observation: InternetObservation, now: datetime | None = None, half_life_days: float = 45.0) -> float:
    now = now or datetime.now(timezone.utc)
    raw = observation.published_at or observation.observed_at
    try:
        then = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0.5
    age_days = max(0.0, (now - then).total_seconds() / 86400.0)
    return round(exp(-0.69314718056 * age_days / half_life_days), 4)


def synthesize_claims(
    observations: Iterable[InternetObservation],
    outcomes: Iterable[OutcomeFeedback] = (),
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[InternetObservation]] = defaultdict(list)
    for item in observations:
        grouped[item.claim_key].append(item)
    feedback: dict[str, list[OutcomeFeedback]] = defaultdict(list)
    for item in outcomes:
        feedback[item.claim_key].append(item)

    result: list[dict[str, Any]] = []
    for claim_key, rows in grouped.items():
        groups = {row.independent_group or _domain(row.source_url) for row in rows}
        weighted = [source_reliability(row) * freshness_weight(row, now=now) for row in rows]
        confidence = 1.0
        for value in weighted:
            confidence *= 1.0 - value
        confidence = 1.0 - confidence
        primary = any(row.primary_source for row in rows)
        verified = feedback.get(claim_key, [])
        successes = sum(item.success for item in verified)
        failures = len(verified) - successes
        if verified:
            outcome_rate = (successes + 1.0) / (len(verified) + 2.0)
            confidence = 0.65 * confidence + 0.35 * outcome_rate
        if verified and failures == 0 and successes > 0:
            level = "validated"
        elif primary or len(groups) >= 2:
            level = "supported"
        else:
            level = "hypothesis" if confidence >= 0.35 else "observation"
        result.append({
            "claim_key": claim_key,
            "claim": rows[-1].claim,
            "promotion_level": level,
            "confidence": round(max(0.0, min(0.99, confidence)), 4),
            "source_count": len(rows),
            "independent_source_groups": len(groups),
            "primary_source_present": primary,
            "verified_outcomes": len(verified),
            "successful_outcomes": successes,
            "failed_outcomes": failures,
            "observations": [asdict(row) for row in rows],
        })
    return sorted(result, key=lambda row: row["confidence"], reverse=True)


def learning_directives(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    directives: list[dict[str, Any]] = []
    for row in claims:
        level = str(row.get("promotion_level") or "observation")
        confidence = float(row.get("confidence") or 0.0)
        if level in {"observation", "hypothesis"}:
            action = "seek_independent_corroboration_before_action"
        elif level == "supported" and confidence < 0.75:
            action = "run_bounded_low_risk_test"
        elif level == "validated":
            action = "increase_strategy_weight_with_exploration_reserve"
        else:
            action = "retain_without_promotion"
        directives.append({
            "claim_key": row.get("claim_key"),
            "promotion_level": level,
            "confidence": confidence,
            "action": action,
            "external_submission_authorized": False,
        })
    return directives
