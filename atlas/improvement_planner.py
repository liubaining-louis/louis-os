"""Prioritize improvements from deterministic diagnostics."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ImprovementProposal:
    capability: str
    title: str
    rationale: str
    impact: float
    confidence: float
    effort: float
    priority: float
    acceptance_criteria: list[str]
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TEMPLATES: dict[str, dict[str, Any]] = {
    "autonomous_execution": {
        "title": "Complete one approved external action end-to-end",
        "impact": 9.0,
        "confidence": 0.8,
        "effort": 5.0,
        "criteria": [
            "An approved action transitions from queued to completed or blocked",
            "Every external side effect has a timestamped evidence record",
            "Human intervention is requested only for KYC, payment, signature or strong authentication",
        ],
    },
    "monetization": {
        "title": "Run a measurable monetization experiment",
        "impact": 10.0,
        "confidence": 0.65,
        "effort": 6.0,
        "criteria": [
            "One experiment is registered before execution",
            "Costs, elapsed time and outcome are recorded",
            "Revenue is reported only with verifiable payment evidence",
        ],
    },
    "evidence_discipline": {
        "title": "Strengthen the external evidence pipeline",
        "impact": 8.0,
        "confidence": 0.9,
        "effort": 3.0,
        "criteria": [
            "Each autonomous action emits an immutable evidence item",
            "Evidence includes source, timestamp, action and outcome",
            "Claims without evidence are marked unverified",
        ],
    },
    "opportunity_research": {
        "title": "Improve opportunity qualification precision",
        "impact": 7.0,
        "confidence": 0.8,
        "effort": 4.0,
        "criteria": [
            "Candidates are checked for freshness, eligibility and reward terms",
            "Duplicate or closed candidates are rejected",
            "Top candidates include an executable next-action dossier",
        ],
    },
    "memory": {
        "title": "Audit persistent memory reliability",
        "impact": 6.0,
        "confidence": 0.9,
        "effort": 3.0,
        "criteria": [
            "Write/read continuity is tested across process restarts",
            "Memory failures are surfaced in runtime state",
            "Retention limits are deterministic and documented",
        ],
    },
}


def plan(diagnostic: Mapping[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    proposals: list[ImprovementProposal] = []
    for weakness in diagnostic.get("weaknesses") or []:
        capability = str(weakness.get("name"))
        template = _TEMPLATES.get(capability)
        if not template:
            continue
        score = float(weakness.get("score") or 0)
        impact = float(template["impact"])
        confidence = float(template["confidence"])
        effort = max(float(template["effort"]), 1.0)
        urgency = max(0.1, (10.0 - score) / 10.0)
        priority = round((impact * confidence * urgency) / effort, 4)
        gaps = "; ".join(weakness.get("gaps") or ["Capability below target"])
        proposals.append(
            ImprovementProposal(
                capability=capability,
                title=str(template["title"]),
                rationale=f"Current score {score}/10. {gaps}",
                impact=impact,
                confidence=confidence,
                effort=effort,
                priority=priority,
                acceptance_criteria=list(template["criteria"]),
            )
        )
    proposals.sort(key=lambda item: (-item.priority, item.capability))
    return [item.to_dict() for item in proposals[: max(1, limit)]]
