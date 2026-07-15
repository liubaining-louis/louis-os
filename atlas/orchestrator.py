from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from .core import build_plan, validate_plan
from .providers import complete


_AGENT_ROLES = {
    "research": "Research Agent: investigate the question, separate evidence from assumptions, and identify missing information.",
    "code": "Engineering Agent: propose technically sound, testable implementation steps and identify failure modes.",
    "communication": "Communication Agent: produce a clear, accurate message while preserving intent and constraints.",
    "transaction": "Risk Agent: analyse the requested external action, risks, prerequisites, and approval requirements. Do not execute it.",
    "general": "Generalist Agent: solve the objective methodically and state assumptions, risks, and next actions.",
}


@dataclass(frozen=True)
class StageTrace:
    stage: str
    agent: str
    status: str
    output: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    mission_type: str
    workflow: str
    risk_level: str
    requires_approval: bool
    final_answer: str
    traces: list[StageTrace]
    revision_count: int
    provider: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["traces"] = [trace.to_dict() for trace in self.traces]
        return payload


def _memory_block(memories: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in memories[:5]:
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(
                f"- [{item.get('memory_type', 'fact')}/{item.get('domain', 'general')}; "
                f"confidence={float(item.get('confidence', 0.0)):.2f}] {content}"
            )
    return "\n".join(lines)


def _needs_revision(critique: str) -> bool:
    first_line = critique.strip().splitlines()[0].upper() if critique.strip() else ""
    return "REVISE" in first_line or "FAIL" in first_line


def orchestrate_mission(
    mission_type: str,
    objective: str,
    context: dict[str, Any],
    memories: list[dict[str, Any]] | None = None,
) -> OrchestrationResult:
    plan = build_plan(objective, context)
    valid, errors = validate_plan(plan)
    if not valid:
        raise ValueError("invalid plan: " + "; ".join(errors))

    traces: list[StageTrace] = [
        StageTrace(
            stage="planning",
            agent="Planner",
            status="completed",
            output=str(plan.to_dict()),
        )
    ]

    if plan.requires_external_action:
        answer = (
            "Human approval is required before this external action can be executed. "
            "The request has been classified as high risk and no action was performed."
        )
        traces.append(StageTrace("approval_gate", "Risk Agent", "approval_required", answer))
        return OrchestrationResult(
            status="approval_required",
            mission_type=plan.mission_type,
            workflow=plan.workflow,
            risk_level=plan.risk_level,
            requires_approval=True,
            final_answer=answer,
            traces=traces,
            revision_count=0,
            provider="none",
            model="none",
        )

    memory_context = _memory_block(memories or [])
    specialist_role = _AGENT_ROLES.get(plan.mission_type, _AGENT_ROLES["general"])
    specialist_prompt = (
        f"{specialist_role}\n"
        f"Objective: {objective}\n"
        f"Mission type requested: {mission_type}\n"
        f"Selected workflow: {plan.workflow}\n"
        f"Context: {context}\n"
    )
    if memory_context:
        specialist_prompt += (
            "Potentially relevant durable memory. Treat it as context, not verified truth:\n"
            f"{memory_context}\n"
        )
    specialist_prompt += (
        "Produce a draft with these headings: Analysis, Verified facts, Assumptions, Risks, Missing information, Recommended actions."
    )
    draft_response = complete(specialist_prompt)
    draft = draft_response.text
    traces.append(StageTrace("specialist", f"{plan.mission_type.title()} Agent", "completed", draft))

    critic_prompt = (
        "You are the Louis OS Critic Agent. Evaluate the draft against the objective for correctness, completeness, "
        "unsupported claims, safety, and actionability. Start the first line with exactly VERDICT: PASS or VERDICT: REVISE. "
        "Then give concise reasons and precise corrections.\n"
        f"Objective: {objective}\nDraft:\n{draft}"
    )
    critic_response = complete(critic_prompt)
    critique = critic_response.text
    traces.append(StageTrace("critique", "Critic Agent", "completed", critique))

    revision_count = 0
    max_revisions = min(max(int(os.environ.get("ORCHESTRATOR_MAX_REVISIONS", "1")), 0), 2)
    candidate = draft
    if _needs_revision(critique) and max_revisions > 0:
        revision_prompt = (
            f"{specialist_role}\nRevise the draft using every valid criticism. Do not mention the review process.\n"
            f"Objective: {objective}\nOriginal draft:\n{draft}\nCritique:\n{critique}"
        )
        revision_response = complete(revision_prompt)
        candidate = revision_response.text
        revision_count = 1
        traces.append(StageTrace("revision", f"{plan.mission_type.title()} Agent", "completed", candidate))

    synthesis_prompt = (
        "You are the Louis OS Synthesizer Agent. Return the final professional answer only. Preserve verified facts, "
        "clearly label assumptions, highlight risks and missing information, and finish with prioritized next actions. "
        "Do not invent sources or claim that an external action was performed.\n"
        f"Objective: {objective}\nCandidate answer:\n{candidate}\nCritic review:\n{critique}"
    )
    final_response = complete(synthesis_prompt)
    final_answer = final_response.text
    traces.append(StageTrace("synthesis", "Synthesizer Agent", "completed", final_answer))

    return OrchestrationResult(
        status="completed",
        mission_type=plan.mission_type,
        workflow=plan.workflow,
        risk_level=plan.risk_level,
        requires_approval=False,
        final_answer=final_answer,
        traces=traces,
        revision_count=revision_count,
        provider=final_response.provider,
        model=final_response.model,
    )
