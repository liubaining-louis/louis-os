from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

from atlas.experiment_outcomes import ExperimentEvaluation

ActionKind = Literal["prepare_scale", "revise_experiment", "archive_venture"]


@dataclass(frozen=True)
class VentureNextAction:
    experiment_id: str
    action_kind: ActionKind
    priority: int
    objective: str
    tasks: tuple[str, ...]
    rationale: tuple[str, ...]
    external_execution_allowed: bool = False
    status: str = "queued"

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id is required")
        if self.priority not in {1, 2, 3}:
            raise ValueError("priority must be 1, 2 or 3")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if not self.tasks:
            raise ValueError("at least one task is required")
        if not self.rationale:
            raise ValueError("rationale is required")
        if self.external_execution_allowed:
            raise ValueError("next actions must remain internal until separately authorized")


class VentureNextActionPlanner:
    """Convert experiment decisions into bounded internal work without external execution."""

    def plan(self, evaluation: ExperimentEvaluation) -> VentureNextAction:
        if not evaluation.experiment_id.strip():
            raise ValueError("evaluation experiment_id is required")
        if evaluation.decision == "continue":
            action = VentureNextAction(
                experiment_id=evaluation.experiment_id,
                action_kind="prepare_scale",
                priority=1,
                objective="Prepare the next evidence-backed scale stage without external execution.",
                tasks=(
                    "summarize validated evidence and remaining uncertainties",
                    "define the smallest reversible scale hypothesis",
                    "prepare a bounded resource and risk budget",
                    "stage all external actions in dry-run mode for separate authorization",
                ),
                rationale=evaluation.reasons,
            )
        elif evaluation.decision == "revise":
            action = VentureNextAction(
                experiment_id=evaluation.experiment_id,
                action_kind="revise_experiment",
                priority=2,
                objective="Revise one material assumption and run one bounded follow-up experiment.",
                tasks=(
                    "identify the weakest assumption from the evaluation evidence",
                    "change exactly one offer, target or method variable",
                    "preserve the original success metric for comparison",
                    "prepare a new dry-run experiment artifact",
                ),
                rationale=evaluation.reasons,
            )
        elif evaluation.decision == "stop":
            action = VentureNextAction(
                experiment_id=evaluation.experiment_id,
                action_kind="archive_venture",
                priority=3,
                objective="Stop resource consumption while preserving reusable learning.",
                tasks=(
                    "record the stop decision and supporting evidence",
                    "extract reusable market, offer and execution lessons",
                    "release any reserved internal capacity",
                    "mark the experiment as ineligible for automatic reactivation",
                ),
                rationale=evaluation.reasons,
            )
        else:
            raise ValueError(f"unsupported experiment decision: {evaluation.decision}")
        action.validate()
        return action

    def plan_many(self, evaluations: Iterable[ExperimentEvaluation]) -> list[VentureNextAction]:
        actions = [self.plan(evaluation) for evaluation in evaluations]
        return sorted(actions, key=lambda item: (item.priority, item.experiment_id))

    def write(self, actions: Iterable[VentureNextAction], output_path: str | Path) -> str:
        items = list(actions)
        for item in items:
            item.validate()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "action_count": len(items),
            "actions": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
