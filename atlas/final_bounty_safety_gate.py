"""Final fail-closed safety gate for bounty candidates and backlog entries."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .narrow_payable_scout import ScoutOutcome
from .safe_convertible_bounty_scout import SAFE_QUERIES, discover_safe_convertible_registry

_FINAL_REJECTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "context_or_instruction_exfiltration",
        re.compile(
            r"generation_context|boot_context|paste everything.{0,140}(?:before|prior|context|task|human)|"
            r"all instructions,? guidelines,? and configuration|everything (?:that )?(?:appeared|was provided).{0,120}(?:context|task)|"
            r"complete and unmodified.{0,120}(?:context|instructions|configuration)",
            re.I | re.S,
        ),
    ),
    (
        "chained_eligibility_prerequisite",
        re.compile(
            r"must first complete\s*\[#?\d+|before you are eligible to work on this issue|"
            r"complete issue\s*#?\d+\s+first",
            re.I,
        ),
    ),
)


def final_safety_reasons(candidate: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    text = f"{candidate.get('title', '')}\n{candidate.get('body', '')}"
    reasons: list[str] = []
    evidence: list[str] = []
    for code, pattern in _FINAL_REJECTIONS:
        match = pattern.search(text)
        if match:
            reasons.append(code)
            evidence.append(match.group(0).strip()[:260])
    return list(dict.fromkeys(reasons)), list(dict.fromkeys(evidence))


def discover_final_safe_registry(
    getter=None,
    *,
    queries: Sequence[str] = SAFE_QUERIES,
    **kwargs,
) -> ScoutOutcome:
    outcome = discover_safe_convertible_registry(getter=getter, queries=queries, **kwargs)
    registry = dict(outcome.registry)
    rejected = list(outcome.rejected)

    safe_candidates: list[dict[str, Any]] = []
    for candidate in registry.get("candidates") or []:
        reasons, evidence = final_safety_reasons(candidate)
        if reasons:
            rejected.append(
                {
                    "candidate_id": candidate.get("id"),
                    "url": candidate.get("url"),
                    "title": candidate.get("title"),
                    "reason": "final_safety_gate_rejected",
                    "safety_reasons": reasons,
                    "safety_evidence": evidence,
                    "prior_status": candidate.get("status"),
                }
            )
        else:
            safe_candidates.append(candidate)

    safe_backlog: list[dict[str, Any]] = []
    for candidate in registry.get("credible_backlog") or []:
        reasons, evidence = final_safety_reasons(candidate)
        if reasons:
            rejected.append(
                {
                    "candidate_id": candidate.get("id"),
                    "url": candidate.get("url"),
                    "title": candidate.get("title"),
                    "reason": "final_safety_gate_rejected",
                    "safety_reasons": reasons,
                    "safety_evidence": evidence,
                    "prior_status": candidate.get("status"),
                }
            )
        else:
            safe_backlog.append(candidate)

    registry.update(
        {
            "schema_version": 6,
            "count": len(safe_candidates),
            "authenticity_verified": len(safe_candidates),
            "authenticity_blocked": len(rejected),
            "credible_candidates": len(safe_candidates),
            "provider_backed_candidates": len(safe_candidates) + len(safe_backlog),
            "narrow_candidates": len(safe_candidates) + len(safe_backlog),
            "convertible_candidates": len(safe_candidates),
            "credible_backlog_count": len(safe_backlog),
            "candidates": safe_candidates,
            "credible_backlog": safe_backlog,
            "final_safety_gate": "active",
            "root_cause_code": None if safe_candidates else "no_final_safe_convertible_payable_candidate",
        }
    )
    return ScoutOutcome(
        registry=registry,
        inspected=outcome.inspected,
        qualified=len(safe_candidates),
        rejected=tuple(rejected),
        errors=outcome.errors,
        queries=outcome.queries,
    )
