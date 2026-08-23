#!/usr/bin/env python3
"""Prioritize small paid missions and persist exact human-gate notifications."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.cash_first_market import (
    build_cash_first_portfolio,
    human_action_payload,
    prioritize_capability_backlog,
)
from atlas.automation_compatibility import reject_incompatible_delivery_methods

RESULTS = ROOT / "results"
MARKET_PATH = RESULTS / "universal_market_opportunities.json"
PORTFOLIO_PATH = RESULTS / "cash_first_market.json"
HUMAN_ACTION_PATH = RESULTS / "human_action_required.json"
BACKLOG_PATH = RESULTS / "capability_backlog.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"
LEDGER_PATH = RESULTS / "monetization.json"
REJECTION_REGISTRY_PATH = ROOT / "config" / "persistent_opportunity_rejections.json"
PREPARED_ARTIFACTS_PATH = ROOT / "config" / "prepared_opportunity_artifacts.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def attach_prepared_artifacts(
    rows: list[dict[str, Any]], registry: Any, *, root: Path = ROOT
) -> list[dict[str, Any]]:
    entries = registry.get("items") if isinstance(registry, dict) else []
    entries = [item for item in entries or [] if isinstance(item, dict) and item.get("active") is not False]
    output: list[dict[str, Any]] = []
    for raw in rows:
        item = dict(raw)
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if str(decision.get("status") or "") == "rejected":
            output.append(item)
            continue
        opportunity_id = str(item.get("opportunity_id") or "")
        source_url = str(item.get("source_url") or "").rstrip("/")
        match = next(
            (
                entry
                for entry in entries
                if str(entry.get("opportunity_id") or "") == opportunity_id
                and str(entry.get("source_url") or "").rstrip("/") == source_url
            ),
            None,
        )
        if not match:
            output.append(item)
            continue
        paths = [str(value) for value in match.get("artifact_paths") or [] if str(value).strip()]
        expected_hashes = match.get("sha256") if isinstance(match.get("sha256"), dict) else {}
        verified = bool(paths)
        for relative in paths:
            path = root / relative
            if not path.is_file():
                verified = False
                break
            expected = str(expected_hashes.get(relative) or "")
            if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                verified = False
                break
        metadata = dict(item.get("metadata") or {})
        metadata["prepared_artifact_registry_match"] = True
        metadata["prepared_artifact_registry_verified"] = verified
        if verified:
            metadata["submission_dossier_prepared"] = True
            metadata["prepared_artifacts"] = paths
            metadata["proposal_path"] = paths[0]
            if len(paths) > 1:
                metadata["proposal_manifest_path"] = paths[1]
            metadata["human_action_instructions"] = [
                str(value) for value in match.get("human_action_instructions") or [] if str(value).strip()
            ]
        item["metadata"] = metadata
        output.append(item)
    return output


def main() -> int:
    market = load_json(MARKET_PATH, {})
    if not isinstance(market, dict) or not isinstance(market.get("opportunities"), list):
        raise SystemExit("universal market evidence is missing or invalid")

    # Defense in depth: several narrower workflows invoke this post-processor
    # without running the dedicated compatibility step first. Never let such a
    # workflow resurrect an opportunity already rejected by policy.
    safe_rows, _ = reject_incompatible_delivery_methods(
        [item for item in market["opportunities"] if isinstance(item, dict)],
        persistent_rejections=load_json(REJECTION_REGISTRY_PATH, {"items": []}),
    )
    market["opportunities"] = attach_prepared_artifacts(
        safe_rows,
        load_json(PREPARED_ARTIFACTS_PATH, {"items": []}),
    )
    save_json(MARKET_PATH, market)

    previous_human = load_json(HUMAN_ACTION_PATH, {"items": []})
    previous_fingerprints = {
        str(item.get("notification_fingerprint") or "")
        for item in previous_human.get("items", [])
        if isinstance(item, dict) and item.get("notification_fingerprint")
    }

    portfolio = build_cash_first_portfolio(market)
    human = human_action_payload(portfolio)
    new_items = [
        item
        for item in human.get("items", [])
        if str(item.get("notification_fingerprint") or "") not in previous_fingerprints
    ]
    human["new_count"] = len(new_items)
    human["new_items"] = new_items
    human["notification_required"] = bool(new_items)
    backlog = prioritize_capability_backlog(load_json(BACKLOG_PATH, {"items": []}), portfolio)

    save_json(PORTFOLIO_PATH, portfolio)
    save_json(HUMAN_ACTION_PATH, human)
    save_json(BACKLOG_PATH, backlog)

    counts = portfolio["counts"]
    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "cash_first_candidates": counts["cash_first"],
            "strategic_candidates": counts["strategic"],
            "human_action_ready": counts["human_action_ready"],
            "new_human_actions": human["new_count"],
            "owner_notification_required": human["notification_required"],
            "cash_first_top_opportunity": portfolio.get("top_cash_first"),
            "next_action": (
                "notify_owner_and_complete_exact_human_gate"
                if human["notification_required"]
                else "route_top_cash_first_mission_to_executor"
                if counts["cash_first"]
                else "activate_next_small_mission_source"
            ),
        }
    )
    evidence = list(cycle.get("evidence") or [])
    for path in (PORTFOLIO_PATH, HUMAN_ACTION_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence:
            evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    ledger = load_json(LEDGER_PATH, {})
    ledger.update(
        {
            "cash_first_engine": "active",
            "cash_first_candidates": counts["cash_first"],
            "strategic_candidates": counts["strategic"],
            "human_action_ready": counts["human_action_ready"],
            "new_human_actions": human["new_count"],
            "owner_notification_required": human["notification_required"],
            "next_action": cycle["next_action"],
            "cash_first_top_opportunity": portfolio.get("top_cash_first"),
        }
    )
    save_json(LEDGER_PATH, ledger)

    print(
        json.dumps(
            {
                "cash_first": counts["cash_first"],
                "strategic": counts["strategic"],
                "human_action_ready": counts["human_action_ready"],
                "new_human_actions": human["new_count"],
                "next_action": cycle["next_action"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
