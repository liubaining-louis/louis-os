from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MissionPlan:
    mission_type: str
    workflow: str
    risk_level: str
    requires_external_action: bool
    steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Rules are ordered from highest to lowest risk. This prevents an objective such
# as "send an email" from being classified as a harmless communication task.
_RULES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    (
        "transaction",
        (
            "buy", "purchase", "pay", "order", "send", "delete", "deploy",
            "achet", "paie", "commande", "envoie", "supprime", "déploie",
        ),
        "approval_workflow",
        "high",
    ),
    (
        "communication",
        ("email", "message", "reply", "post", "mail", "répond"),
        "communication_workflow",
        "medium",
    ),
    (
        "code",
        ("code", "implement", "build", "develop", "fix", "test", "développ", "corrig"),
        "engineering_workflow",
        "medium",
    ),
    (
        "research",
        ("research", "analyse", "compare", "find", "study", "étud", "cherche"),
        "research_workflow",
        "low",
    ),
)


def classify_mission(objective: str) -> tuple[str, str, str]:
    normalized = objective.casefold()
    for mission_type, keywords, workflow, risk_level in _RULES:
        if any(keyword in normalized for keyword in keywords):
            return mission_type, workflow, risk_level
    return "general", "general_workflow", "low"


def build_plan(objective: str, context: dict[str, Any] | None = None) -> MissionPlan:
    if not objective or not objective.strip():
        raise ValueError("objective must not be empty")
    if context is not None and not isinstance(context, dict):
        raise TypeError("context must be a dictionary")

    mission_type, workflow, risk_level = classify_mission(objective)
    external = risk_level == "high"
    steps = ["validate_input", "prepare_context", "execute_workflow", "evaluate_output"]
    if external:
        steps.insert(-1, "request_human_approval")

    return MissionPlan(
        mission_type=mission_type,
        workflow=workflow,
        risk_level=risk_level,
        requires_external_action=external,
        steps=steps,
    )


def validate_plan(plan: MissionPlan) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not plan.steps:
        errors.append("plan has no steps")
    if plan.steps and plan.steps[0] != "validate_input":
        errors.append("plan must start with validate_input")
    if plan.steps and plan.steps[-1] != "evaluate_output":
        errors.append("plan must end with evaluate_output")
    if plan.risk_level == "high" and "request_human_approval" not in plan.steps:
        errors.append("high-risk plan requires human approval")
    if plan.requires_external_action != (plan.risk_level == "high"):
        errors.append("external-action flag is inconsistent with risk level")
    return not errors, errors
