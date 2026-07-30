from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from atlas.internet_opportunity_router import next_pivot, route_all

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "internet_opportunity_router.json"
INPUT_PATHS = (
    ROOT / "results" / "universal_market_opportunities.json",
    ROOT / "results" / "simple_mission_source_refresh.json",
    ROOT / "results" / "small_bounty_source_refresh.json",
    ROOT / "results" / "software_micro_mission_classification.json",
    ROOT / "results" / "cash_first_market.json",
    ROOT / "results" / "monetization.json",
    ROOT / "results" / "universal_market_cycle.json",
)
LIST_KEYS = {
    "opportunities",
    "items",
    "candidates",
    "results",
    "market_opportunities",
    "simple_mission_opportunities",
    "universal_market_opportunities",
    "qualified_opportunities",
    "ranked_opportunities",
}
TOP_KEYS = {
    "cash_first_top_opportunity",
    "top_opportunity",
    "top_candidate",
    "selected",
}
MAX_ITEMS_TOTAL = 80
MAX_ITEMS_PER_SOURCE = 20


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _first(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _number(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _candidate_like(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        _first(
            value,
            "opportunity_id",
            "title",
            "source_url",
            "canonical_url",
            "url",
        )
    )


def _walk_candidates(value: Any, *, parent_key: str = "") -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        if parent_key in LIST_KEYS:
            for item in value:
                if _candidate_like(item):
                    yield item
        return
    if not isinstance(value, dict):
        return
    for key, nested in value.items():
        if key in TOP_KEYS and _candidate_like(nested):
            yield nested
        elif key in LIST_KEYS and isinstance(nested, list):
            for item in nested:
                if _candidate_like(item):
                    yield item


def normalize_candidate(item: dict[str, Any], source_file: str) -> dict[str, Any]:
    normalized = dict(item)
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    payment_evidence = item.get("payment_evidence") if isinstance(item.get("payment_evidence"), list) else []
    payment_methods = item.get("payment_methods") if isinstance(item.get("payment_methods"), list) else []
    if not payment_methods and isinstance(metadata.get("payment_methods"), list):
        payment_methods = list(metadata.get("payment_methods") or [])
    human_actions = item.get("human_actions") if isinstance(item.get("human_actions"), list) else []

    normalized["title"] = str(_first(item, "title", "name", default="Untitled opportunity"))
    normalized["description"] = str(_first(item, "description", "summary", "body", default=""))
    normalized["source_url"] = str(
        _first(item, "source_url", "canonical_url", "url", default=evidence[0] if evidence else "")
    )
    normalized["opportunity_id"] = str(
        _first(item, "opportunity_id", "id", default=normalized["source_url"] or normalized["title"])
    )
    normalized["effort_hours"] = _number(
        _first(
            item,
            "effort_hours",
            "estimated_effort_hours",
            default=metadata.get("estimated_effort_hours"),
        ),
        999.0,
    )
    normalized["reward_eur"] = max(
        0.0,
        _number(_first(item, "reward_eur", "reward_amount", "reward"), 0.0),
    )
    normalized["competition_risk"] = max(
        0.0,
        min(1.0, _number(_first(item, "competition_risk", "competition"), 0.5)),
    )

    explicit_payment_confidence = _first(item, "payment_confidence", "payment_probability")
    if explicit_payment_confidence is None:
        explicit_payment_confidence = 0.85 if item.get("reward_verified") and payment_evidence else 0.0
    normalized["payment_confidence"] = max(
        0.0,
        min(1.0, _number(explicit_payment_confidence, 0.0)),
    )

    explicit_fit = _first(item, "capability_fit", "validated_product_fit")
    if explicit_fit is not None:
        normalized["capability_fit"] = max(0.0, min(1.0, _number(explicit_fit, 0.0)))
    else:
        normalized.pop("capability_fit", None)

    normalized["human_actions_required"] = _integer(
        _first(item, "human_actions_required", default=len(human_actions)),
        len(human_actions),
    )
    if normalized["human_actions_required"] == 0 and item.get("account_required"):
        normalized["human_actions_required"] = 1

    normalized["payment_path"] = str(
        _first(item, "payment_path", default=payment_methods[0] if payment_methods else "")
    )
    if not normalized["payment_path"] and item.get("reward_verified") and payment_evidence:
        normalized["payment_path"] = "verified public reward evidence; payout terms require platform confirmation"

    acceptance = _first(item, "acceptance_criteria", "deliverables")
    if not acceptance and metadata.get("source_kind") == "public_freelance_listing" and normalized["description"]:
        acceptance = ["deliver the bounded scope described in the verified public listing"]
    normalized["acceptance_criteria"] = acceptance or []

    days_left = _integer(metadata.get("days_left"), 0)
    normalized["fresh_open_verified"] = bool(
        item.get("fresh_open_verified") is True
        or item.get("status_verified_open") is True
        or metadata.get("status_verified_open") is True
        or (
            metadata.get("source_kind") == "public_freelance_listing"
            and bool(item.get("observed_at"))
            and days_left > 0
        )
    )
    normalized["legal_policy_pass"] = bool(
        item.get("legal_policy_pass") is True
        or metadata.get("legal_policy_pass") is True
        or metadata.get("official_source") is True
    )
    normalized["market_signal_verified"] = bool(
        item.get("market_signal_verified") is True
        or metadata.get("official_source") is True
        or normalized["source_url"]
    )
    normalized["personal_eligibility_required"] = bool(
        item.get("personal_eligibility_required")
        or item.get("live_attendance_required")
    )
    normalized["active_competing_claim"] = bool(item.get("active_competing_claim"))
    normalized["source_file"] = source_file
    normalized["source_id"] = str(
        _first(item, "source_id", "collector_source_id", default=metadata.get("collector_source_id") or source_file)
    )
    normalized["upstream_decision"] = _first(decision, "status", default=item.get("decision_status"))
    return normalized


def extract_items(payloads: Iterable[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    for source_file, payload in payloads:
        for raw in _walk_candidates(payload):
            if source_counts.get(source_file, 0) >= MAX_ITEMS_PER_SOURCE:
                break
            item = normalize_candidate(raw, source_file)
            key = str(item.get("opportunity_id") or item.get("source_url") or item.get("title"))
            existing = deduped.get(key)
            if existing is None or len(item.get("description", "")) > len(existing.get("description", "")):
                deduped[key] = item
            source_counts[source_file] = source_counts.get(source_file, 0) + 1
            if len(deduped) >= MAX_ITEMS_TOTAL:
                return list(deduped.values())
    return list(deduped.values())


def build_cycle(payloads: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    payload_list = list(payloads)
    items = extract_items(payload_list)
    routed = route_all(items)
    decisions = {name: 0 for name in ("execute_now", "prepare_then_gate", "capability_build", "reject")}
    domains: dict[str, dict[str, int]] = {}
    sources: dict[str, dict[str, int]] = {}
    for item in routed:
        state = item["internet_opportunity_router"]
        decisions[state["decision"]] += 1
        domain = state["domain"]
        source = str(item.get("source_id") or item.get("source_file") or "unknown")
        domains.setdefault(domain, {"seen": 0, "eligible": 0, "execute_now": 0, "prepare_then_gate": 0, "capability_build": 0, "reject": 0})
        sources.setdefault(source, {"seen": 0, "eligible": 0, "reject": 0})
        domains[domain]["seen"] += 1
        domains[domain][state["decision"]] += 1
        sources[source]["seen"] += 1
        if state["decision"] in {"execute_now", "prepare_then_gate"}:
            domains[domain]["eligible"] += 1
            sources[source]["eligible"] += 1
        elif state["decision"] == "reject":
            sources[source]["reject"] += 1

    market = next((payload for name, payload in payload_list if name == "universal_market_cycle.json"), {})
    metrics = {
        "rejected_without_candidate": decisions["reject"] if not decisions["execute_now"] and not decisions["prepare_then_gate"] else 0,
        "source_results_without_eligible": sum(row["seen"] for row in sources.values() if row["eligible"] == 0),
        "proposals_without_reply": max(0, _integer(market.get("outreach_sent"), 0) - _integer(market.get("qualified_replies"), 0)),
        "replies_without_conversion": max(0, _integer(market.get("qualified_replies"), 0) - _integer(market.get("conversions"), 0)),
        "verified_payments": 1 if _number(_first(market, "revenue_received", "revenue_verified_eur"), 0.0) > 0 else 0,
    }
    pivot = next_pivot(metrics)
    selected = next((item for item in routed if item["internet_opportunity_router"]["decision"] == "execute_now"), None)
    if selected is None:
        selected = next((item for item in routed if item["internet_opportunity_router"]["decision"] == "prepare_then_gate"), None)

    return {
        "schema_version": "1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "adaptive multidomain Internet opportunity discovery and execution",
        "allocation": {"exploit": 0.50, "adjacent": 0.30, "experimental": 0.20},
        "input_files": [name for name, _ in payload_list],
        "items_seen": len(items),
        "sources_seen": len(sources),
        "domains_seen": len(domains),
        "decision_counts": decisions,
        "domain_metrics": domains,
        "source_metrics": sources,
        "selected": selected,
        "top_ranked": routed[:20],
        "pivot_metrics": metrics,
        "next_pivot": pivot,
        "next_action": (
            "prepare execution dossier for selected opportunity"
            if selected
            else "regenerate capability-specific queries across under-tested domains and replace low-yield sources"
        ),
        "truth": {
            "external_submission_verified": False,
            "payment_verified": False,
            "revenue_verified_eur": _number(_first(market, "revenue_received", "revenue_verified_eur"), 0.0),
            "forecast_only_not_pipeline_or_revenue": True,
        },
    }


def main() -> None:
    payloads = [(path.name, load_json(path)) for path in INPUT_PATHS]
    output = build_cycle(payloads)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
