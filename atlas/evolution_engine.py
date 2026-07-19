"""Guarded self-improvement orchestration for Louis OS.

V1 diagnoses the live system, prioritizes measurable improvements and persists a
single active proposal. It never edits production code or deploys by itself.
Promotion remains evidence-gated through a pull request and CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.improvement_planner import plan
from atlas.louis_state import snapshot
from atlas.self_diagnostic import diagnose

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_id(proposal: dict[str, Any]) -> str:
    material = json.dumps(
        {"capability": proposal.get("capability"), "title": proposal.get("title")},
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def build_cycle(state: dict[str, Any] | None = None) -> dict[str, Any]:
    observed = state or snapshot()
    diagnostic = diagnose(observed)
    proposals = plan(diagnostic)
    selected = proposals[0] if proposals else None
    if selected:
        selected = dict(selected)
        selected["proposal_id"] = _proposal_id(selected)
        selected["status"] = "proposed"
        selected["requires_pr_and_ci"] = True
        selected["automatic_production_deploy"] = False

    return {
        "schema_version": 1,
        "created_at": _now(),
        "engine": "louis-evolution-engine-v1",
        "diagnostic": diagnostic,
        "proposals": proposals,
        "selected_improvement": selected,
        "guardrails": {
            "no_direct_main_mutation": True,
            "no_automatic_production_deploy": True,
            "tests_required": True,
            "benchmark_required": True,
            "rollback_required": True,
            "external_claims_require_evidence": True,
        },
    }


def persist_local(cycle: dict[str, Any]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    target = RESULTS / "evolution_cycle_latest.json"
    target.write_text(json.dumps(cycle, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def persist_firestore(cycle: dict[str, Any]) -> None:
    from google.cloud import firestore

    client = firestore.Client(project=PROJECT_ID)
    selected = cycle.get("selected_improvement") or {}
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    client.collection("louis_self_diagnostics").document(cycle_id).set(cycle)
    client.collection("louis_evolution_runtime").document("current").set(
        {
            "last_cycle_at": cycle["created_at"],
            "overall_score": cycle["diagnostic"]["overall_score"],
            "selected_improvement": selected,
            "engine": cycle["engine"],
        },
        merge=True,
    )
    if selected:
        client.collection("louis_improvement_queue").document(selected["proposal_id"]).set(
            selected,
            merge=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firestore", action="store_true", help="Persist verified cycle state to Firestore")
    parser.add_argument("--print", dest="print_output", action="store_true")
    args = parser.parse_args()

    cycle = build_cycle()
    target = persist_local(cycle)
    if args.firestore:
        persist_firestore(cycle)
    if args.print_output:
        print(json.dumps(cycle, ensure_ascii=False, indent=2))
    else:
        print(f"Evolution cycle written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
