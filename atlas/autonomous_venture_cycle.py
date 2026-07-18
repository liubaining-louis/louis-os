from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from atlas.venture_builder import VentureExperiment
from atlas.venture_runtime import (
    CeoAgent,
    JsonlVentureMemory,
    Opportunity,
    VentureDecisionEngine,
    VentureEvent,
    build_dry_run_artifact,
)


BASELINE_47_REFERENCE = "github://liubaining-louis/louis-os/issues/47"


@dataclass(frozen=True)
class BaselineSnapshot:
    decision_score: float
    autonomy: float
    unsupported_claims: int = 0
    reference: str = BASELINE_47_REFERENCE

    def validate(self) -> None:
        if not self.reference.strip():
            raise ValueError("baseline reference is required")
        if not 0 <= self.decision_score <= 1:
            raise ValueError("baseline decision_score must be between 0 and 1")
        if not 0 <= self.autonomy <= 1:
            raise ValueError("baseline autonomy must be between 0 and 1")
        if self.unsupported_claims < 0:
            raise ValueError("baseline unsupported_claims must be non-negative")


@dataclass(frozen=True)
class ExperimentObservation:
    metric_name: str
    metric_value: float
    evidence_references: list[str]
    unsupported_claims: int = 0

    def validate(self) -> None:
        if not self.metric_name.strip():
            raise ValueError("metric_name is required")
        if not 0 <= self.metric_value <= 1:
            raise ValueError("metric_value must be between 0 and 1")
        if not self.evidence_references:
            raise ValueError("experiment observation requires evidence references")
        if self.unsupported_claims < 0:
            raise ValueError("unsupported_claims must be non-negative")


@dataclass(frozen=True)
class VentureCycleResult:
    venture_id: str
    selected_opportunity_id: str
    status: str
    promoted: bool
    reasons: list[str]
    baseline_reference: str
    decision_score: float
    autonomy: float
    metric_name: str | None
    metric_value: float | None
    artifact_paths: dict[str, str]


class AutonomousVentureCycle:
    """Run one bounded AVB cycle without performing unapproved external actions."""

    def __init__(self, engine: VentureDecisionEngine | None = None) -> None:
        self.engine = engine or VentureDecisionEngine()
        self.ceo = CeoAgent(self.engine)

    def run(
        self,
        *,
        venture_id: str,
        opportunities: Iterable[Opportunity],
        baseline: BaselineSnapshot,
        output_dir: str | Path,
        success_threshold: float,
        observation: ExperimentObservation | None = None,
        external_action: bool = False,
        approval_granted: bool = False,
    ) -> VentureCycleResult:
        if not venture_id.strip():
            raise ValueError("venture_id is required")
        if not 0 <= success_threshold <= 1:
            raise ValueError("success_threshold must be between 0 and 1")
        baseline.validate()
        if observation is not None:
            observation.validate()

        candidates = list(opportunities)
        ranked = self.engine.rank(candidates)
        decision = self.ceo.decide(candidates)
        selected = next(
            item.opportunity
            for item in ranked
            if item.opportunity.opportunity_id == decision.selected_opportunity_id
        )

        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        memory = JsonlVentureMemory(root / "venture-memory.jsonl")

        memory.append(
            VentureEvent(
                event_type="opportunity_observed",
                venture_id=venture_id,
                payload={"candidate_count": len(candidates)},
                evidence_references=sorted(
                    {reference for item in candidates for reference in item.evidence_references}
                ),
            )
        )
        memory.append(
            VentureEvent(
                event_type="hypothesis_selected",
                venture_id=venture_id,
                payload={
                    "opportunity_id": selected.opportunity_id,
                    "decision_score": decision.score,
                },
                evidence_references=selected.evidence_references,
            )
        )

        decision_path = root / "decision.json"
        build_dry_run_artifact(venture_id, decision, ranked, decision_path)
        memory.append(
            VentureEvent(
                event_type="asset_built",
                venture_id=venture_id,
                payload={"path": str(decision_path)},
            )
        )

        experiment = VentureExperiment(
            experiment_id=f"{venture_id}-validation-1",
            hypothesis=(
                f"The offer '{selected.proposed_offer}' can reach a validation score "
                f"of at least {success_threshold:.3f}."
            ),
            action="Run a bounded internal validation and record evidence-backed results.",
            success_metric="validation_score",
            success_threshold=str(success_threshold),
            deadline="one_cycle",
            stop_condition="Stop after one observation or before any unapproved external action.",
            budget_limit=0.0,
            idempotency_key=f"{venture_id}:validation:1",
            requires_approval=external_action,
            evidence_references=selected.evidence_references,
        )
        experiment.validate()
        experiment_path = root / "experiment.json"
        experiment_path.write_text(
            json.dumps(asdict(experiment), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        memory.append(
            VentureEvent(
                event_type="experiment_planned",
                venture_id=venture_id,
                payload={"path": str(experiment_path), "external_action": external_action},
            )
        )

        artifact_paths = {
            "decision": str(decision_path),
            "experiment": str(experiment_path),
            "memory": str(memory.path),
        }

        if external_action and not approval_granted:
            reasons = ["external action requires human approval"]
            result = VentureCycleResult(
                venture_id=venture_id,
                selected_opportunity_id=selected.opportunity_id,
                status="approval_required",
                promoted=False,
                reasons=reasons,
                baseline_reference=baseline.reference,
                decision_score=decision.score,
                autonomy=selected.autonomy,
                metric_name=None,
                metric_value=None,
                artifact_paths=artifact_paths,
            )
            return self._write_result(root, memory, result, evidence_references=[])

        if observation is None:
            reasons = ["no measurable observation was supplied"]
            result = VentureCycleResult(
                venture_id=venture_id,
                selected_opportunity_id=selected.opportunity_id,
                status="measurement_required",
                promoted=False,
                reasons=reasons,
                baseline_reference=baseline.reference,
                decision_score=decision.score,
                autonomy=selected.autonomy,
                metric_name=None,
                metric_value=None,
                artifact_paths=artifact_paths,
            )
            return self._write_result(root, memory, result, evidence_references=[])

        reasons: list[str] = []
        if observation.metric_value < success_threshold:
            reasons.append("success threshold was not reached")
        if decision.score < baseline.decision_score:
            reasons.append("decision score regressed versus mission #47 baseline")
        if selected.autonomy < baseline.autonomy:
            reasons.append("autonomy regressed versus mission #47 baseline")
        if observation.unsupported_claims > baseline.unsupported_claims:
            reasons.append("unsupported claims increased versus mission #47 baseline")

        result = VentureCycleResult(
            venture_id=venture_id,
            selected_opportunity_id=selected.opportunity_id,
            status="learned",
            promoted=not reasons,
            reasons=reasons,
            baseline_reference=baseline.reference,
            decision_score=decision.score,
            autonomy=selected.autonomy,
            metric_name=observation.metric_name,
            metric_value=observation.metric_value,
            artifact_paths=artifact_paths,
        )
        return self._write_result(
            root,
            memory,
            result,
            evidence_references=observation.evidence_references,
        )

    @staticmethod
    def _write_result(
        root: Path,
        memory: JsonlVentureMemory,
        result: VentureCycleResult,
        *,
        evidence_references: list[str],
    ) -> VentureCycleResult:
        result_path = root / "result.json"
        payload = asdict(result)
        payload["artifact_paths"] = {**result.artifact_paths, "result": str(result_path)}
        result_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        memory.append(
            VentureEvent(
                event_type="result_recorded" if evidence_references else "cycle_blocked",
                venture_id=result.venture_id,
                payload={
                    "status": result.status,
                    "promoted": result.promoted,
                    "reasons": result.reasons,
                    "path": str(result_path),
                },
                evidence_references=evidence_references,
            )
        )
        return VentureCycleResult(
            **{
                **asdict(result),
                "artifact_paths": payload["artifact_paths"],
            }
        )
