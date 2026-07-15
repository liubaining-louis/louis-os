from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from .core import build_plan, validate_plan
from .memory import format_memory_context
from .output_contract import validate_output_contract
from .providers import complete


_AGENT_ROLES = {
    "research": "Research Agent: investigate the question, separate evidence from assumptions, and identify missing information.",
    "code": "Engineering Agent: propose technically sound, testable implementation steps and identify failure modes.",
    "communication": "Communication Agent: produce a clear, accurate message while preserving intent and constraints.",
    "transaction": "Risk Agent: analyse the requested external action, risks, prerequisites, and approval requirements. Do not execute it.",
    "general": "Generalist Agent: solve the objective methodically and state assumptions, risks, and next actions.",
}
_DEFAULT_MAX_REVISIONS = 1
_MAX_ALLOWED_REVISIONS = 2
_DEFAULT_TRACE_CHARS = 12000


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


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _clip(value: str) -> str:
    limit = _bounded_int("ORCHESTRATOR_TRACE_MAX_CHARS", _DEFAULT_TRACE_CHARS, 1000, 50000)
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[trace truncated]"


def _trace(stage: str, agent: str, status: str, output: str) -> StageTrace:
    return StageTrace(stage=stage, agent=agent, status=status, output=_clip(output))


def _needs_revision(critique: str) -> bool:
    if not critique.strip():
        return True
    first_line = critique.strip().splitlines()[0].strip().upper()
    return first_line in {"VERDICT: REVISE", "VERDICT: FAIL"}


def _critic_prompt(objective: str, candidate: str) -> str:
    return (
        "You are the Louis OS Critic Agent. Evaluate the candidate against every explicit requirement in the objective "
        "for correctness, completeness, unsupported claims, calculations, safety, and actionability. Never pass a report "
        "that omits a requested table, ranking, formula, timeline, qualification questions, contact sequence, or final decision. "
        "Start the first line with exactly VERDICT: PASS or VERDICT: REVISE. Then list precise missing deliverables.\n"
        f"Objective: {objective}\nCandidate:\n{candidate}"
    )


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
        _trace("planning", "Planner", "completed", json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True))
    ]

    if plan.requires_external_action:
        answer = (
            "Human approval is required before this external action can be executed. "
            "The request has been classified as high risk and no action was performed."
        )
        traces.append(_trace("approval_gate", "Risk Agent", "approval_required", answer))
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

    memory_context = format_memory_context(memories or [], max_chars=4000)
    specialist_role = _AGENT_ROLES.get(plan.mission_type, _AGENT_ROLES["general"])
    specialist_prompt = (
        f"{specialist_role}\n"
        "Treat the objective as a binding output contract. Complete every requested deliverable explicitly. "
        "Show calculations and formulas when requested. Do not replace requested work with suggestions to collect data.\n"
        f"Objective: {objective}\n"
        f"Mission type requested: {mission_type}\n"
        f"Selected workflow: {plan.workflow}\n"
        f"Context: {json.dumps(context, ensure_ascii=False, sort_keys=True)}\n"
    )
    if memory_context:
        specialist_prompt += (
            "Potentially relevant durable memory. Treat it as context, not verified truth:\n"
            f"{memory_context}\n"
        )
    specialist_prompt += (
        "Produce a structured draft. Separate verified facts, assumptions and missing information. "
        "For quantitative requests, include readable tables and explicit arithmetic."
    )

    response = complete(specialist_prompt)
    candidate = response.text
    traces.append(_trace("specialist", f"{plan.mission_type.title()} Agent", "completed", candidate))

    critic_response = complete(_critic_prompt(objective, candidate))
    critique = critic_response.text
    traces.append(_trace("critique", "Critic Agent", "completed", critique))

    revision_count = 0
    max_revisions = _bounded_int(
        "ORCHESTRATOR_MAX_REVISIONS", _DEFAULT_MAX_REVISIONS, 0, _MAX_ALLOWED_REVISIONS
    )
    while _needs_revision(critique) and revision_count < max_revisions:
        revision_prompt = (
            f"{specialist_role}\n"
            "Revise the candidate using every valid criticism and satisfy every explicit deliverable in the objective. "
            "Do not mention the review process. Do not omit requested calculations, rankings, timelines or decisions.\n"
            f"Objective: {objective}\nCandidate:\n{candidate}\nCritique:\n{critique}"
        )
        revision_response = complete(revision_prompt)
        candidate = revision_response.text
        revision_count += 1
        traces.append(
            _trace(f"revision_{revision_count}", f"{plan.mission_type.title()} Agent", "completed", candidate)
        )

        critic_response = complete(_critic_prompt(objective, candidate))
        critique = critic_response.text
        traces.append(
            _trace(f"critique_{revision_count + 1}", "Critic Agent", "completed", critique)
        )

    synthesis_prompt = (
        "You are the Louis OS Synthesizer Agent. Return the final professional answer only. The objective is a binding "
        "output contract: preserve every requested table, formula, ranking, timeline, question list, contact sequence and "
        "decision. Preserve verified facts, clearly label assumptions, highlight risks and missing information. "
        "Do not invent sources or claim that an external action was performed.\n"
        f"Objective: {objective}\nCandidate answer:\n{candidate}\nLatest critic review:\n{critique}"
    )
    final_response = complete(synthesis_prompt)
    final_answer = final_response.text
    traces.append(_trace("synthesis", "Synthesizer Agent", "completed", final_answer))

    validation = validate_output_contract(objective, final_answer)
    traces.append(
        _trace(
            "output_validation",
            "Deterministic Validator",
            "completed" if validation.valid else "failed_validation",
            json.dumps({"valid": validation.valid, "errors": validation.errors}, ensure_ascii=False),
        )
    )

    if not validation.valid:
        repair_prompt = (
            f"{specialist_role}\n"
            "Repair the report. Return a complete final answer satisfying the objective and every deterministic validation "
            "error below. Include the missing content rather than promising future work.\n"
            f"Objective: {objective}\nCurrent answer:\n{final_answer}\n"
            f"Validation errors: {json.dumps(validation.errors, ensure_ascii=False)}"
        )
        repair_response = complete(repair_prompt)
        final_answer = repair_response.text
        revision_count += 1
        traces.append(_trace("contract_repair", f"{plan.mission_type.title()} Agent", "completed", final_answer))
        validation = validate_output_contract(objective, final_answer)
        traces.append(
            _trace(
                "output_revalidation",
                "Deterministic Validator",
                "completed" if validation.valid else "failed_validation",
                json.dumps({"valid": validation.valid, "errors": validation.errors}, ensure_ascii=False),
            )
        )
        final_response = repair_response

    status = "completed" if validation.valid else "failed_validation"
    if not validation.valid:
        final_answer = (
            "OUTPUT VALIDATION FAILED. The generated report was not accepted because required deliverables were missing: "
            + ", ".join(validation.errors)
            + "\n\nLast generated draft:\n"
            + final_answer
        )

    return OrchestrationResult(
        status=status,
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
