from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from atlas.initiative import ActionBudget, Opportunity, select_opportunity


@dataclass(frozen=True)
class CycleObservation:
    source: str
    reference: str
    summary: str


@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    status: str
    stages: tuple[str, ...]
    selected_opportunity: str | None
    plan: str | None
    simulated_result: str | None
    evaluation: str
    learned: str
    approval_required: bool = False


class JsonlCycleStore:
    """Append-only local cycle store with idempotent cycle identifiers."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, cycle_id: str) -> CycleRecord | None:
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("cycle_id") == cycle_id:
                payload["stages"] = tuple(payload["stages"])
                return CycleRecord(**payload)
        return None

    def append_once(self, record: CycleRecord) -> CycleRecord:
        existing = self.get(record.cycle_id)
        if existing is not None:
            return existing
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record


def build_cycle_id(observations: Iterable[CycleObservation], opportunities: Iterable[Opportunity]) -> str:
    observation_payload = sorted(
        (asdict(item) for item in observations),
        key=lambda item: (item["source"], item["reference"], item["summary"]),
    )
    opportunity_payload = sorted(
        (
            {
                "key": item.key,
                "impact": item.impact,
                "urgency": item.urgency,
                "confidence": item.confidence,
                "effort": item.effort,
                "risk": item.risk,
                "requires_approval": item.requires_approval,
            }
            for item in opportunities
        ),
        key=lambda item: item["key"],
    )
    encoded = json.dumps(
        {"observations": observation_payload, "opportunities": opportunity_payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def run_dry_cycle(
    *,
    observations: Iterable[CycleObservation],
    opportunities: Iterable[Opportunity],
    budget: ActionBudget,
    store: JsonlCycleStore,
    planner: Callable[[Opportunity, tuple[CycleObservation, ...]], str],
    simulator: Callable[[Opportunity, str], Mapping[str, object]],
) -> CycleRecord:
    observation_items = tuple(observations)
    opportunity_items = tuple(opportunities)
    cycle_id = build_cycle_id(observation_items, opportunity_items)
    existing = store.get(cycle_id)
    if existing is not None:
        return existing

    stages = ("observe", "prioritize")
    selected = select_opportunity(opportunity_items, budget)
    if selected is None:
        approval_required = any(item.requires_approval for item in opportunity_items)
        record = CycleRecord(
            cycle_id=cycle_id,
            status="approval_required" if approval_required else "no_action",
            stages=stages + ("evaluate", "learn"),
            selected_opportunity=None,
            plan=None,
            simulated_result=None,
            evaluation="No opportunity passed the action budget and approval gates.",
            learned="Retain rejected opportunities for a later cycle with changed evidence or approval.",
            approval_required=approval_required,
        )
        return store.append_once(record)

    plan = planner(selected, observation_items).strip()
    if not plan:
        raise ValueError("planner must return a non-empty plan")
    result = dict(simulator(selected, plan))
    passed = result.get("passed") is True
    regression = result.get("regression") is True
    evidence = str(result.get("evidence", "")).strip()
    if not evidence:
        raise ValueError("simulation must provide evidence")

    promoted = passed and not regression
    status = "validated" if promoted else "rejected"
    evaluation = evidence if promoted else f"Promotion refused: {evidence}"
    learned = (
        "Dry-run hypothesis validated; retain evidence for production validation."
        if promoted
        else "Hypothesis rejected; do not repeat without new evidence or a changed implementation."
    )
    record = CycleRecord(
        cycle_id=cycle_id,
        status=status,
        stages=stages + ("plan", "simulate", "evaluate", "learn"),
        selected_opportunity=selected.key,
        plan=plan,
        simulated_result=evidence,
        evaluation=evaluation,
        learned=learned,
    )
    return store.append_once(record)
