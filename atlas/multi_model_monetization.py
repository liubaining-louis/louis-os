from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adaptive_model_router import assess_difficulty
from .providers import ModelResponse, complete_with


@dataclass(frozen=True)
class TeamResult:
    fingerprint: str
    status: str
    selected_candidate_id: str | None
    fast_provider: str | None
    reasoning_provider: str | None
    critic_pass: bool
    recommendation: str
    revision_required: bool
    evidence: list[str]
    raw: dict[str, Any]


def _stable_candidate_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "title", "source", "url", "reward", "reward_amount", "currency",
        "payment_path", "deadline", "readiness_status", "execution_score", "score",
        "authenticity_verified", "external_prerequisites_cleared", "requires_user_validation",
        "acceptance_criteria", "deliverable_type", "estimated_hours",
    )
    return {key: candidate.get(key) for key in keys if key in candidate}


def candidate_fingerprint(candidates: Sequence[Mapping[str, Any]], artifact_sha256: str | None = None) -> str:
    payload = {
        "candidates": [_stable_candidate_view(item) for item in candidates[:5]],
        "artifact_sha256": artifact_sha256 or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model_response_missing_json")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("model_response_not_object")
    return payload


def _call(provider: str, prompt: str) -> tuple[ModelResponse, dict[str, Any]]:
    response = complete_with(provider, prompt)
    return response, _extract_json(response.text)


def run_team_review(
    candidates: Sequence[Mapping[str, Any]],
    *,
    artifact_text: str | None = None,
    artifact_sha256: str | None = None,
) -> TeamResult:
    ranked = sorted(
        [dict(item) for item in candidates],
        key=lambda item: (-float(item.get("execution_score", 0) or 0), -float(item.get("score", 0) or 0)),
    )[:5]
    fingerprint = candidate_fingerprint(ranked, artifact_sha256)
    if not ranked:
        return TeamResult(fingerprint, "blocked", None, None, None, False, "reject", False, [], {"reason": "no_candidates"})

    fast_provider = os.getenv("LLM_FAST_PROVIDER", "groq").strip().casefold() or "groq"
    reasoning_provider = os.getenv("LLM_REASONING_PROVIDER", "vertex").strip().casefold() or "vertex"

    scout_prompt = (
        "You are the fast opportunity triage specialist. Rank these paid opportunities for an autonomous agent. "
        "Return JSON only with selected_candidate_id, shortlist_ids, reject_ids, rationale, estimated_hours, risk_flags. "
        "Do not claim submission or payment. Candidates:\n" + json.dumps(ranked, ensure_ascii=False, default=str)
    )
    fast_response, scout = _call(fast_provider, scout_prompt)
    selected_id = str(scout.get("selected_candidate_id") or "") or str(ranked[0].get("id") or "")
    selected = next((item for item in ranked if str(item.get("id")) == selected_id), ranked[0])
    selected_id = str(selected.get("id") or selected_id or "") or None

    difficulty_prompt = json.dumps(selected, ensure_ascii=False, default=str) + " verify submission payment risk acceptance criteria"
    difficulty = asdict(assess_difficulty(difficulty_prompt))

    reasoning_prompt = (
        "You are the senior reasoning specialist. Analyze the selected opportunity and return JSON only with: "
        "recommendation (execute_now|prepare_then_gate|reject), acceptance_criteria, missing_information, "
        "payment_path_verified (boolean), submission_channel_verified (boolean), risk_flags, execution_plan. "
        "Never infer payment or submission evidence that is not present. Opportunity:\n" + json.dumps(selected, ensure_ascii=False, default=str)
    )
    reasoning_response, reasoning = _call(reasoning_provider, reasoning_prompt)

    critic_payload = {"opportunity": selected, "reasoning": reasoning, "artifact": artifact_text or ""}
    critic_prompt = (
        "You are the independent critic before any external submission. Return JSON only with: "
        "critic_pass (boolean), defects, unmet_acceptance_criteria, evidence_gaps, revision_instructions. "
        "Fail closed if acceptance criteria, payment path, submission channel, or artifact compliance are not proven.\n"
        + json.dumps(critic_payload, ensure_ascii=False, default=str)
    )
    critic_response, critic = _call(reasoning_provider, critic_prompt)
    critic_pass = critic.get("critic_pass") is True

    revision_required = not critic_pass
    revision: dict[str, Any] = {}
    if revision_required:
        revision_prompt = (
            "You are the revision specialist. Based on the critic, return JSON only with: revised_plan, "
            "remaining_blockers, recommendation (prepare_then_gate|reject), submission_safe (boolean). "
            "Do not fabricate missing evidence.\n" + json.dumps({"selected": selected, "reasoning": reasoning, "critic": critic}, ensure_ascii=False, default=str)
        )
        _, revision = _call(reasoning_provider, revision_prompt)

    recommendation = str(reasoning.get("recommendation") or "reject")
    if not critic_pass:
        recommendation = str(revision.get("recommendation") or "prepare_then_gate")
    if recommendation not in {"execute_now", "prepare_then_gate", "reject"}:
        recommendation = "reject"

    evidence = [f"model:{fast_response.provider}/{fast_response.model}", f"model:{reasoning_response.provider}/{reasoning_response.model}"]
    return TeamResult(
        fingerprint=fingerprint,
        status="completed",
        selected_candidate_id=selected_id,
        fast_provider=fast_response.provider,
        reasoning_provider=reasoning_response.provider,
        critic_pass=critic_pass,
        recommendation=recommendation,
        revision_required=revision_required,
        evidence=evidence,
        raw={"scout": scout, "difficulty": difficulty, "reasoning": reasoning, "critic": critic, "revision": revision},
    )
