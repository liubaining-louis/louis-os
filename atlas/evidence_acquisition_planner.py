from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

EvidenceType = Literal["demand", "competition", "pricing", "feasibility", "risk"]
ResearchMethod = Literal["web_search", "official_registry", "marketplace_scan", "supplier_check", "customer_signal_review"]


@dataclass(frozen=True)
class EvidenceGap:
    evidence_type: EvidenceType
    urgency: float
    uncertainty: float
    expected_value_of_information: float

    def validate(self) -> None:
        if self.evidence_type not in {"demand", "competition", "pricing", "feasibility", "risk"}:
            raise ValueError("unsupported evidence_type")
        for name in ("urgency", "uncertainty", "expected_value_of_information"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    evidence_type: EvidenceType
    method: ResearchMethod
    query: str
    priority: float
    maximum_sources: int
    maximum_cost_score: float
    stop_condition: str


class EvidenceAcquisitionPlanner:
    """Convert evidence gaps into bounded, deterministic research tasks."""

    METHOD_MAP: dict[EvidenceType, ResearchMethod] = {
        "demand": "customer_signal_review",
        "competition": "web_search",
        "pricing": "marketplace_scan",
        "feasibility": "supplier_check",
        "risk": "official_registry",
    }

    def __init__(self, *, maximum_tasks: int = 5, maximum_sources_per_task: int = 4, total_cost_score: float = 0.20) -> None:
        if maximum_tasks <= 0 or maximum_sources_per_task <= 0:
            raise ValueError("task and source limits must be positive")
        if not 0 <= total_cost_score <= 1:
            raise ValueError("total_cost_score must be between 0 and 1")
        self.maximum_tasks = maximum_tasks
        self.maximum_sources_per_task = maximum_sources_per_task
        self.total_cost_score = total_cost_score

    def plan(self, mission_id: str, objective: str, gaps: Iterable[EvidenceGap]) -> list[ResearchTask]:
        if not mission_id.strip() or not objective.strip():
            raise ValueError("mission_id and objective are required")
        ranked: list[tuple[EvidenceGap, float]] = []
        for gap in gaps:
            gap.validate()
            score = 0.35 * gap.urgency + 0.30 * gap.uncertainty + 0.35 * gap.expected_value_of_information
            ranked.append((gap, round(score, 6)))
        ranked.sort(key=lambda item: (-item[1], item[0].evidence_type))
        selected = ranked[: self.maximum_tasks]
        if not selected:
            return []
        total_priority = sum(score for _, score in selected) or 1.0
        tasks: list[ResearchTask] = []
        for index, (gap, priority) in enumerate(selected, start=1):
            share = priority / total_priority
            tasks.append(ResearchTask(
                task_id=f"{mission_id}-research-{index}",
                evidence_type=gap.evidence_type,
                method=self.METHOD_MAP[gap.evidence_type],
                query=f"{objective} — collect recent, reliable evidence for {gap.evidence_type}",
                priority=priority,
                maximum_sources=self.maximum_sources_per_task,
                maximum_cost_score=round(self.total_cost_score * share, 6),
                stop_condition="Stop when two independent reliable sources corroborate the claim or the source limit is reached.",
            ))
        return tasks

    def write(self, tasks: Iterable[ResearchTask], output_path: str | Path) -> str:
        items = list(tasks)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "task_count": len(items), "tasks": [asdict(item) for item in items]}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
