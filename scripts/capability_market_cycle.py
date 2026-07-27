#!/usr/bin/env python3
"""Run mission clustering and market-backed capability planning.

The script updates internal planning artifacts only. It never creates an account,
submits a proposal, signs terms, changes payout settings or records revenue.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.capability_market import (
    build_capability_plans,
    cluster_opportunities,
    enrich_capability_backlog,
    market_payload,
    reject_ai_prohibited_opportunities,
    simulate_cluster_revenue,
)

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
LEDGER_PATH = RESULTS / "monetization.json"
CAPABILITY_CONFIG = ROOT / "config" / "universal_capabilities.json"
CAPABILITY_MARKET_PATH = RESULTS / "capability_market.json"
CLUSTERS_PATH = RESULTS / "mission_clusters.json"
SIMULATION_PATH = RESULTS / "revenue_simulation.json"
BUILD_PLAN_PATH = RESULTS / "capability_build_plan.json"
TEMPLATES_ROOT = RESULTS / "cluster_proposal_templates"
HISTORY_PATH = RESULTS / "capability_market_history.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def capability_statuses(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id") or ""): str(item.get("status") or "unknown")
        for item in payload.get("capabilities") or []
        if isinstance(item, Mapping) and str(item.get("id") or "")
    }


def template_text(cluster: Mapping[str, Any]) -> str:
    family = str(cluster.get("deliverable_family") or "bounded digital deliverable")
    capability = str(cluster.get("capability_id") or "")
    return "\n".join(
        [
            f"# Reusable proposal template — {family}",
            "",
            f"Capability: `{capability}`",
            f"Cluster: `{cluster.get('cluster_id')}`",
            "External submission: false",
            "",
            "## Client-facing draft",
            "Hello,",
            "",
            "I can deliver this bounded scope after confirming the exact inputs, output format and acceptance criteria. My process is to produce a reviewable first artifact, validate completeness and consistency, then deliver the final version with a concise validation note.",
            "",
            "Before starting, please confirm that the public description contains the complete scope and that all required source material may be shared through the platform.",
            "",
            "Regards",
            "",
            "## Adaptation checklist",
            "- preserve the payer's exact scope, currency, budget evidence and deadline;",
            "- state only capabilities and experience supported by evidence;",
            "- replace generic validation steps with the cluster-specific test plan;",
            "- reject work that prohibits AI, automation or the authorized delivery method;",
            "- do not submit until the truthful account and terms gate is authorized;",
            "- preserve the platform receipt after any real submission.",
            "",
            "This template is preparation evidence only. It is not a proposal receipt, contract, pipeline or revenue.",
        ]
    )


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, dict) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    normalized, rejected_ai = reject_ai_prohibited_opportunities(
        [item for item in market["opportunities"] if isinstance(item, Mapping)]
    )
    market["opportunities"] = normalized
    save_json(MARKET_PATH, market)

    statuses = capability_statuses(load_json(CAPABILITY_CONFIG, {}))
    clusters = cluster_opportunities(normalized, statuses)
    plans = build_capability_plans(clusters)
    capability_market = market_payload(clusters, plans, rejected_ai)
    simulations = [simulate_cluster_revenue(cluster, normalized) for cluster in clusters]

    save_json(CAPABILITY_MARKET_PATH, capability_market)
    save_json(
        CLUSTERS_PATH,
        {
            "schema_version": "1.0",
            "generated_at": capability_market["generated_at"],
            "count": len(clusters),
            "clusters": [cluster.to_dict() for cluster in clusters],
        },
    )
    save_json(
        SIMULATION_PATH,
        {
            "schema_version": "1.0",
            "generated_at": capability_market["generated_at"],
            "type": "simulation_only",
            "counted_as_pipeline": False,
            "counted_as_revenue": False,
            "annualization_status": "insufficient_history",
            "simulations": simulations,
        },
    )
    save_json(
        BUILD_PLAN_PATH,
        {
            "schema_version": "1.0",
            "generated_at": capability_market["generated_at"],
            "count": len(plans),
            "top_plan": plans[0].to_dict() if plans else None,
            "plans": [plan.to_dict() for plan in plans],
            "external_actions_authorized": False,
            "external_submissions_verified": 0,
            "revenue_verified_eur": 0.0,
        },
    )

    backlog = load_json(BACKLOG_PATH, {"items": []})
    enriched = enrich_capability_backlog(backlog if isinstance(backlog, Mapping) else {"items": []}, clusters, plans)
    enriched["generated_at"] = capability_market["generated_at"]
    save_json(BACKLOG_PATH, enriched)

    if TEMPLATES_ROOT.exists():
        shutil.rmtree(TEMPLATES_ROOT)
    TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
    template_paths: list[str] = []
    for cluster in clusters:
        if cluster.lane != "cash_first":
            continue
        path = TEMPLATES_ROOT / f"{cluster.cluster_id}.md"
        path.write_text(template_text(cluster.to_dict()), encoding="utf-8")
        template_paths.append(str(path.relative_to(ROOT)))

    history = load_json(HISTORY_PATH, {"schema_version": "1.0", "snapshots": []})
    snapshots = list(history.get("snapshots") or []) if isinstance(history, Mapping) else []
    snapshots.append(
        {
            "generated_at": capability_market["generated_at"],
            "cluster_count": len(clusters),
            "cash_first_cluster_count": sum(cluster.lane == "cash_first" for cluster in clusters),
            "top_capability": clusters[0].capability_id if clusters else None,
            "top_score": clusters[0].capability_market_score if clusters else 0.0,
            "qualified_opportunity_count": sum(cluster.opportunity_count for cluster in clusters),
        }
    )
    save_json(HISTORY_PATH, {"schema_version": "1.0", "snapshots": snapshots[-168:]})

    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "generated_at": capability_market["generated_at"],
            "capability_market_engine": "active",
            "mission_clusters": len(clusters),
            "cash_first_mission_clusters": sum(cluster.lane == "cash_first" for cluster in clusters),
            "capability_build_plans": len(plans),
            "ai_prohibited_opportunities_rejected": rejected_ai,
            "cluster_proposal_templates_prepared": len(template_paths),
            "top_capability_market_score": clusters[0].capability_market_score if clusters else 0.0,
            "top_capability_market_id": clusters[0].capability_id if clusters else None,
            "next_action": (
                f"implement_market_ranked_capability:{plans[0].capability_id}"
                if plans
                else "refresh_independent_simple_mission_sources"
            ),
        }
    )
    evidence = list(cycle.get("evidence") or [])
    for path in (CAPABILITY_MARKET_PATH, CLUSTERS_PATH, SIMULATION_PATH, BUILD_PLAN_PATH, HISTORY_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence:
            evidence.append(relative)
    for path in template_paths:
        if path not in evidence:
            evidence.append(path)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    if isinstance(ledger, dict):
        ledger.update(
            {
                "updated_at": capability_market["generated_at"],
                "capability_market_engine": "active",
                "mission_cluster_count": len(clusters),
                "cash_first_mission_cluster_count": sum(cluster.lane == "cash_first" for cluster in clusters),
                "capability_build_plan_count": len(plans),
                "ai_prohibited_opportunities_rejected": rejected_ai,
                "cluster_proposal_templates_prepared": len(template_paths),
                "capability_market_top": clusters[0].to_dict() if clusters else None,
                "revenue_simulation_type": "simulation_only",
                "revenue_simulation_counted_as_pipeline": False,
                "revenue_simulation_counted_as_revenue": False,
                "next_action": cycle["next_action"],
            }
        )
        ledger["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0)
        ledger["internet_actions_submitted"] = int(ledger.get("internet_actions_submitted") or 0)
        ledger["conversions"] = int(ledger.get("conversions") or 0)
        ledger["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
        ledger["revenue_received"] = float(ledger.get("revenue_received") or 0.0)
        save_json(LEDGER_PATH, ledger)

    print(
        json.dumps(
            {
                "clusters": len(clusters),
                "cash_first_clusters": sum(cluster.lane == "cash_first" for cluster in clusters),
                "capability_plans": len(plans),
                "ai_prohibited_rejected": rejected_ai,
                "templates": len(template_paths),
                "top_capability": clusters[0].capability_id if clusters else None,
                "submitted": 0,
                "revenue_eur": 0.0,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
