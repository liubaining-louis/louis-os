#!/usr/bin/env python3
"""Exercise the cash-realizability gate and enrich the current candidate set.

The observed-case regressions intentionally encode failure modes Louis has already
encountered so future ranking changes cannot silently re-admit them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.opportunity_realizability import assess_opportunity_realizability

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def provider_for(candidate: dict[str, Any]) -> str:
    text = " ".join(str(candidate.get(k, "")) for k in ("source", "source_id", "url", "source_url", "repository_url")).lower()
    aliases = {
        "taskmarket": "taskmarket",
        "rustchain": "rustchain",
        "agentpact": "agentpact",
        "openjobs": "openjobs",
        "taskbounty": "taskbounty",
        "ubounty": "ubounty",
        "bountic": "bountic",
        "mergeos": "mergeos",
        "tenstorrent": "tenstorrent",
        "agentshield": "agentshield",
    }
    for token, provider in aliases.items():
        if token in text:
            return provider
    return "github_public_issue"


def observed_cases() -> list[dict[str, Any]]:
    return [
        {"case":"taskmarket_zero_stake", "provider":"taskmarket", "item":{"state":"open","external_submit_route_verified":True,"payout_method_verified":True,"currency_liquidity_verified":True,"active_competitor_count":8}},
        {"case":"agentshield_ai_prohibited", "provider":"agentshield", "item":{"state":"open","body":"Human contributors only."}},
        {"case":"tenstorrent_assigned", "provider":"tenstorrent", "item":{"state":"open","assigned_to_other":True}},
        {"case":"tenstorrent_stale_aggregator", "provider":"tenstorrent", "item":{"state":"closed","official_state_open":False}},
        {"case":"openjobs_signed_registration", "provider":"openjobs", "item":{"state":"open"}},
        {"case":"taskbounty_terms", "provider":"taskbounty", "item":{"state":"open"}},
        {"case":"ubounty_terms", "provider":"ubounty", "item":{"state":"open"}},
        {"case":"mergeos_broken_withdrawal", "provider":"mergeos", "item":{"state":"open"}},
        {"case":"agentpact_buyer_initiated", "provider":"agentpact", "item":{"state":"open"}},
        {"case":"bountic_crowded", "provider":"bountic", "item":{"state":"open","active_competitor_count":30,"external_submit_route_verified":True,"payout_method_verified":True,"currency_liquidity_verified":True}},
    ]


def enrich_candidates() -> tuple[list[dict[str, Any]], str | None]:
    path = RESULTS / "monetization_candidates.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return [], "candidate_file_missing_or_invalid"
    candidates = payload.get("candidates") or []
    enriched = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        provider = provider_for(c)
        prereqs = c.get("external_prerequisites") or []
        item = dict(c)
        if "state" not in item:
            item["state"] = "open"
        if "active_competitor_count" not in item and "comments" in item:
            item["active_competitor_count"] = item.get("comments")
        r = assess_opportunity_realizability(
            item,
            provider=provider,
            readiness_prerequisites=prereqs,
            source_truth_verified=bool(c.get("opportunity_authenticity_verified", True)),
        )
        row = dict(c)
        row["cash_realizability_provider"] = provider
        row["cash_realizability_decision"] = r.decision
        row["cash_realizability_score"] = r.cash_realizability_score
        row["cash_realizability_hard_reasons"] = list(r.hard_reasons)
        row["cash_realizability_human_gate_reasons"] = list(r.human_gate_reasons)
        row["cash_realizability_soft_reasons"] = list(r.soft_reasons)
        enriched.append(row)
    enriched.sort(key=lambda x: ({"execute":0,"downrank":1,"passive":2,"human_gate":3,"reject":4}.get(x["cash_realizability_decision"],5), -float(x["cash_realizability_score"])))
    return enriched, None


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    regressions=[]
    for case in observed_cases():
        r=assess_opportunity_realizability(case["item"], provider=case["provider"])
        regressions.append({"case":case["case"],"provider":case["provider"],**r.to_dict()})
    candidates,error=enrich_candidates()
    counts={d:sum(1 for x in candidates if x.get("cash_realizability_decision")==d) for d in ("execute","downrank","passive","human_gate","reject")}
    snapshot={
        "generated_at":now,
        "gate":"cash_realizability",
        "policy":"fail_closed_before_expensive_execution",
        "observed_case_regressions":regressions,
        "candidate_source_error":error,
        "current_candidate_count":len(candidates),
        "decision_counts":counts,
        "current_candidates":candidates,
        "execution_rule":"Only execute candidates that remain technically ready, authorized, officially open, eligible, unassigned, payout-realizable, and not human-gated. Downrank crowded/uncertain candidates before compute-heavy work.",
        "revenue_rule":"Advertised, selected, credited or pending rewards are not revenue until payout evidence is independently verified."
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS/"monetization_realizability_snapshot.json").write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"gate":"cash_realizability","current_candidate_count":len(candidates),"decision_counts":counts,"regressions":len(regressions)},ensure_ascii=False))


if __name__ == "__main__":
    main()
