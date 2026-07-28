"""Adaptive recovery and source-allocation logic for the cash-first market.

This module learns from the opportunity history without converting stale records into
submissions. It produces a revalidation queue, source-yield metrics, rejection
feedback and explicit search directives for the next cycle.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

_TERMINAL = {"submitted", "rejected", "expired", "closed"}
_RECOVERABLE = {"prepared", "executable", "not_seen_current_cycle"}


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(value: Any, now: datetime) -> float:
    parsed = _parse_time(value)
    if parsed is None:
        return 10_000.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds() / 86_400.0)


def rejection_reason(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
    if metadata.get("policy_rejection"):
        return str(metadata["policy_rejection"])
    blockers = [str(value) for value in decision.get("blockers") or []]
    for blocker in blockers:
        if blocker.startswith("software_scope_rejected:"):
            return blocker.split(":", 1)[1]
    return blockers[0] if blockers else "unclassified_rejection"


def source_metrics(history_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in history_items:
        source_id = str(item.get("source_id") or "unknown")
        grouped[source_id].append(item)

    rows: list[dict[str, Any]] = []
    for source_id, items in grouped.items():
        statuses = Counter(str(item.get("lifecycle_status") or "unknown") for item in items)
        total = len(items)
        prepared = statuses["prepared"] + statuses["executable"] + statuses["submitted"]
        terminal_rejected = statuses["rejected"]
        yield_rate = prepared / total if total else 0.0
        rejection_rate = terminal_rejected / total if total else 0.0
        score = max(0.0, min(100.0, 100.0 * (0.70 * yield_rate + 0.20 * (1.0 - rejection_rate) + 0.10 * min(1.0, total / 10.0))))
        rows.append({
            "source_id": source_id,
            "observed_total": total,
            "prepared_or_better": prepared,
            "rejected": terminal_rejected,
            "yield_rate": round(yield_rate, 4),
            "rejection_rate": round(rejection_rate, 4),
            "allocation_score": round(score, 2),
            "recommended_share": "increase" if score >= 45 else "maintain" if score >= 20 else "decrease",
        })
    rows.sort(key=lambda item: (-item["allocation_score"], -item["observed_total"], item["source_id"]))
    return rows


def recovery_candidates(
    history_items: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    maximum_age_days: float = 14.0,
    maximum: int = 12,
) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for item in history_items:
        status = str(item.get("lifecycle_status") or "")
        if status in _TERMINAL or status not in _RECOVERABLE:
            continue
        age = _days_since(item.get("last_seen_at"), now)
        if age > maximum_age_days:
            continue
        latest = item.get("latest") if isinstance(item.get("latest"), Mapping) else {}
        decision = latest.get("decision") if isinstance(latest.get("decision"), Mapping) else {}
        metadata = latest.get("metadata") if isinstance(latest.get("metadata"), Mapping) else {}
        if metadata.get("external_receipt") or metadata.get("externally_submitted"):
            continue
        reward = float(latest.get("reward_amount") or 0.0)
        effort = float(metadata.get("estimated_effort_hours") or 16.0)
        time_to_cash = int(latest.get("time_to_cash_days") or 30)
        competition = float(latest.get("competition") or 0.5)
        recovery_score = 100.0 * (
            0.30 * max(0.0, 1.0 - age / maximum_age_days)
            + 0.25 * max(0.0, 1.0 - effort / 16.0)
            + 0.20 * max(0.0, 1.0 - time_to_cash / 30.0)
            + 0.15 * max(0.0, 1.0 - competition)
            + 0.10 * (1.0 if status in {"prepared", "executable"} else 0.4)
        )
        candidates.append({
            "opportunity_id": item.get("opportunity_id"),
            "title": item.get("title"),
            "source_id": item.get("source_id"),
            "source_url": item.get("source_url"),
            "last_seen_at": item.get("last_seen_at"),
            "age_days": round(age, 2),
            "previous_status": status,
            "reward_amount": reward,
            "currency": latest.get("currency"),
            "estimated_effort_hours": effort,
            "time_to_cash_days": time_to_cash,
            "recovery_score": round(recovery_score, 2),
            "action": "revalidate_canonical_listing_before_restoring_to_cash_first",
            "submission_allowed": False,
            "revalidation_required": True,
            "prior_blockers": list(decision.get("blockers") or []),
        })
    candidates.sort(key=lambda item: (-item["recovery_score"], item["age_days"], str(item["opportunity_id"])))
    return candidates[:maximum]


def build_search_directives(
    current_items: Sequence[Mapping[str, Any]],
    history_items: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rejection_counts: Counter[str] = Counter()
    capability_success: Counter[str] = Counter()
    for item in current_items:
        decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
        if decision.get("status") == "rejected":
            rejection_counts[rejection_reason(item)] += 1
    for item in history_items:
        if str(item.get("lifecycle_status") or "") not in {"prepared", "executable", "submitted"}:
            continue
        latest = item.get("latest") if isinstance(item.get("latest"), Mapping) else {}
        for capability in latest.get("required_capabilities") or []:
            capability_success[str(capability)] += 1

    directives: list[dict[str, Any]] = []
    for capability, count in capability_success.most_common(5):
        directives.append({
            "priority": "high",
            "type": "capability_reuse",
            "capability_id": capability,
            "reason": f"historically produced {count} prepared-or-better opportunity(ies)",
            "instruction": f"search more independent public sources for bounded {capability} work with explicit budget and <=16h scope",
        })
    for reason, count in rejection_counts.most_common(5):
        directives.append({
            "priority": "medium",
            "type": "negative_query_filter",
            "rejection_reason": reason,
            "reason_count": count,
            "instruction": f"exclude search terms and categories repeatedly producing rejection reason: {reason}",
        })
    weak_sources = [item for item in metrics if item.get("recommended_share") == "decrease"][:5]
    for source in weak_sources:
        directives.append({
            "priority": "medium",
            "type": "source_reallocation",
            "source_id": source.get("source_id"),
            "instruction": "reduce crawl allocation and replace with a new independent official or public source",
            "allocation_score": source.get("allocation_score"),
        })
    if not directives:
        directives.append({
            "priority": "high",
            "type": "cold_start",
            "instruction": "prioritize French-English translation, public web research, spreadsheet cleanup, narrow Python automation and small static website work",
        })
    return directives


def build_recovery_payload(
    current_market: Mapping[str, Any],
    history: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    current_items = [item for item in current_market.get("opportunities") or [] if isinstance(item, Mapping)]
    history_items = [item for item in history.get("items") or [] if isinstance(item, Mapping)]
    metrics = source_metrics(history_items)
    recovery = recovery_candidates(history_items, now=now)
    directives = build_search_directives(current_items, history_items, metrics)
    return {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "objective": "convert historical learning into more lawful, payable and revalidatable cash-first opportunities",
        "source_metrics": metrics,
        "recovery_queue": recovery,
        "search_directives": directives,
        "counts": {
            "history_items": len(history_items),
            "current_items": len(current_items),
            "recovery_candidates": len(recovery),
            "sources_measured": len(metrics),
            "directives": len(directives),
        },
        "truth": {
            "recovered_items_are_submissions": False,
            "canonical_revalidation_required": True,
            "external_submissions_verified": 0,
            "revenue_verified_eur": 0.0,
        },
    }
