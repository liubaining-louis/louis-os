"""Deterministic self-diagnostic for Louis OS.

The diagnostic intentionally relies on verifiable runtime signals instead of LLM
self-scoring. It produces capability scores and a prioritized weakness list.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CapabilityScore:
    name: str
    score: float
    evidence: list[str]
    gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bounded(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def diagnose(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    runtime = dict(snapshot.get("autonomous_worker") or {})
    monetization = dict(snapshot.get("monetization") or {})
    capabilities = set(snapshot.get("verified_capabilities") or [])

    worker_verified = bool(runtime.get("verified"))
    actions = int(runtime.get("actions_submitted") or 0)
    opportunities = int(runtime.get("opportunities_qualified") or 0)
    evidence_items = int(monetization.get("recorded_evidence_items") or 0)
    experiments = int(monetization.get("recorded_experiments") or 0)
    revenue = float(monetization.get("revenue_received_eur") or 0)

    scores = [
        CapabilityScore(
            "memory",
            _bounded(9 if any("Firestore" in x for x in capabilities) else 3),
            ["Firestore persistent memory advertised"] if any("Firestore" in x for x in capabilities) else [],
            [] if any("Firestore" in x for x in capabilities) else ["No verified persistent memory"],
        ),
        CapabilityScore(
            "autonomous_execution",
            _bounded(3 + (3 if worker_verified else 0) + min(actions, 4)),
            [f"worker_verified={worker_verified}", f"actions_submitted={actions}"],
            [] if actions else ["No verified external action submitted"],
        ),
        CapabilityScore(
            "opportunity_research",
            _bounded(3 + (2 if worker_verified else 0) + min(opportunities / 2, 5)),
            [f"opportunities_qualified={opportunities}"],
            [] if opportunities else ["No qualified opportunities"],
        ),
        CapabilityScore(
            "evidence_discipline",
            _bounded(2 + min(evidence_items, 5) + min(experiments, 3)),
            [f"evidence_items={evidence_items}", f"experiments={experiments}"],
            [] if evidence_items else ["No recorded external evidence"],
        ),
        CapabilityScore(
            "monetization",
            _bounded((5 if experiments else 1) + (5 if revenue > 0 else 0)),
            [f"revenue_received_eur={revenue}", f"experiments={experiments}"],
            [] if revenue > 0 else ["No verified revenue received"],
        ),
    ]

    ordered = sorted(scores, key=lambda item: (item.score, item.name))
    return {
        "scores": [item.to_dict() for item in scores],
        "weaknesses": [item.to_dict() for item in ordered[:3]],
        "overall_score": round(sum(item.score for item in scores) / len(scores), 2),
        "method": "deterministic-runtime-evidence-v1",
    }
