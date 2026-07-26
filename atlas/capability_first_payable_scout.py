"""Capability-first discovery of safe, payable and immediately buildable tasks."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .final_bounty_safety_gate import final_safety_reasons
from .narrow_payable_scout import (
    JsonGetter,
    ScoutOutcome,
    _candidate_id,
    _comments_url,
    _qualify_issue,
    _repo_url,
    github_get_json,
    utc_now,
)
from .patch_capabilities import CAPABILITY_QUERIES, classify_patch_capability
from .payable_source_adapters import compatibility_comment, detect_payment_evidence
from .safe_convertible_bounty_scout import _search_pool, assess_task_safety, repository_trust


def discover_capability_first_registry(
    getter: JsonGetter | None = None,
    *,
    queries: Sequence[str] = CAPABILITY_QUERIES,
    max_candidates: int = 10,
    max_inspected: int = 120,
    min_narrowness: float = 40.0,
    max_active_attempts: int = 5,
    min_repository_trust: float = 25.0,
    max_candidates_per_repository: int = 2,
) -> ScoutOutcome:
    getter = getter or github_get_json
    pool, errors = _search_pool(getter, queries, max_inspected)
    qualified: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    repo_cache: dict[str, dict[str, Any]] = {}

    for issue in pool:
        url = str(issue.get("html_url") or "")
        rejection_base = {
            "candidate_id": _candidate_id(url) if url else "unknown",
            "url": url,
            "title": str(issue.get("title") or ""),
        }
        try:
            comments_payload = getter(_comments_url(issue))
            comments = [dict(item) for item in comments_payload if isinstance(item, Mapping)] if isinstance(comments_payload, list) else []
            evidence = detect_payment_evidence(comments)
            if evidence is None:
                rejected.append({**rejection_base, "reason": "verified_payment_adapter_evidence_missing"})
                continue

            safe, safety_reasons, safety_evidence = assess_task_safety(issue)
            if not safe:
                rejected.append(
                    {
                        **rejection_base,
                        "reason": "unsafe_or_manipulative_task",
                        "safety_reasons": safety_reasons,
                        "safety_evidence": safety_evidence,
                    }
                )
                continue

            number = int(issue.get("number") or 0)
            if number <= 0:
                rejected.append({**rejection_base, "reason": "issue_number_unavailable"})
                continue
            qualification_comments = comments + [compatibility_comment(evidence, number)]

            repo_url = _repo_url(issue)
            if repo_url not in repo_cache:
                repo_payload = getter(repo_url)
                repo_cache[repo_url] = dict(repo_payload) if isinstance(repo_payload, Mapping) else {}
            repo = repo_cache[repo_url]

            candidate, rejection = _qualify_issue(
                issue,
                qualification_comments,
                repo,
                min_narrowness=min_narrowness,
            )
            if candidate is None:
                rejected.append(rejection)
                continue

            attempts = int(candidate.get("active_attempts", 0) or 0)
            if attempts > max_active_attempts:
                rejected.append(
                    {
                        **rejection_base,
                        "reason": "overcrowded_bounty",
                        "active_attempts": attempts,
                        "maximum_allowed": max_active_attempts,
                    }
                )
                continue

            trust_score, trust_evidence = repository_trust(repo)
            if trust_score < min_repository_trust:
                rejected.append(
                    {
                        **rejection_base,
                        "reason": "repository_trust_below_threshold",
                        "repository_trust_score": trust_score,
                        "repository_trust_evidence": trust_evidence,
                    }
                )
                continue

            capability = classify_patch_capability(issue)
            candidate.update(
                {
                    "source": "capability_first_verified_payable_source",
                    "reward_hint": evidence.reward_amount,
                    "reward_amount": evidence.reward_amount,
                    "currency": evidence.currency,
                    "payment_provider": evidence.provider,
                    "payment_evidence_type": evidence.evidence_type,
                    "provider_evidence": evidence.to_dict(),
                    "authenticity_evidence": [evidence.evidence_url, evidence.provider_url, evidence.evidence_excerpt],
                    "opportunity_authenticity_evidence": [evidence.evidence_url, evidence.provider_url, evidence.evidence_excerpt],
                    "task_safety_status": "safe",
                    "task_safety_reasons": [],
                    "repository_trust_score": trust_score,
                    "repository_trust_evidence": trust_evidence,
                }
            )

            final_reasons, final_evidence = final_safety_reasons(candidate)
            if final_reasons:
                rejected.append(
                    {
                        **rejection_base,
                        "reason": "final_safety_gate_rejected",
                        "safety_reasons": final_reasons,
                        "safety_evidence": final_evidence,
                    }
                )
                continue

            if capability is None:
                candidate.update(
                    {
                        "patch_handler": "unsupported_without_new_handler",
                        "current_patch_handler_supported": False,
                        "readiness_status": "gated_unsupported_patch_handler",
                        "external_prerequisites": ["bounded_patch_handler_not_implemented"],
                        "external_prerequisites_cleared": False,
                        "status": "credible_backlog_not_executable",
                        "backlog_reason": "no_deterministic_capability_match",
                    }
                )
                backlog.append(candidate)
                continue

            conversion_probability = round(
                max(
                    0.0,
                    min(
                        100.0,
                        float(candidate.get("narrowness_score", 0) or 0) * 0.35
                        + trust_score * 0.25
                        + float(candidate.get("payability_score", 0) or 0) * 0.25
                        + max(0.0, 15.0 - attempts * 3.0),
                    ),
                ),
                1,
            )
            candidate.update(
                {
                    "patch_handler": capability.capability_id,
                    "capability_match": capability.to_dict(),
                    "current_patch_handler_supported": True,
                    "conversion_probability": conversion_probability,
                    "readiness_status": "executable_now",
                    "external_prerequisites": [],
                    "external_prerequisites_cleared": True,
                    "requires_user_validation": False,
                    "status": "qualified_executable",
                }
            )
            qualified.append(candidate)
        except Exception as exc:
            rejected.append(
                {
                    **rejection_base,
                    "reason": "capability_first_qualification_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    def rank(items: list[dict[str, Any]]) -> None:
        items.sort(
            key=lambda item: (
                -float(item.get("conversion_probability", 0) or 0),
                -float(item.get("reward_scope_ratio", 0) or 0),
                str(item.get("id", "")),
            )
        )

    def cap(items: Sequence[dict[str, Any]], total: int) -> list[dict[str, Any]]:
        counts: defaultdict[str, int] = defaultdict(int)
        selected: list[dict[str, Any]] = []
        for item in items:
            repo_name = str(item.get("target_repository") or "unknown")
            if counts[repo_name] >= max_candidates_per_repository:
                continue
            counts[repo_name] += 1
            selected.append(item)
            if len(selected) >= total:
                break
        return selected

    rank(qualified)
    rank(backlog)
    candidates = cap(qualified, max_candidates)
    credible_backlog = cap(backlog, max_candidates)
    registry = {
        "schema_version": 7,
        "generated_at": utc_now(),
        "count": len(candidates),
        "authenticity_verified": len(candidates),
        "authenticity_blocked": len(rejected),
        "credible_candidates": len(candidates),
        "provider_backed_candidates": len(candidates) + len(credible_backlog),
        "narrow_candidates": len(candidates) + len(credible_backlog),
        "convertible_candidates": len(candidates),
        "credible_backlog_count": len(credible_backlog),
        "candidates": candidates,
        "credible_backlog": credible_backlog,
        "errors": errors,
        "recovery_source": "capability_first_verified_payable_scout",
        "payment_adapter_gate": "active",
        "capability_match_gate": "active",
        "final_safety_gate": "active",
        "root_cause_code": None if candidates else "no_capability_matched_verified_payable_candidate",
    }
    return ScoutOutcome(
        registry=registry,
        inspected=len(pool),
        qualified=len(candidates),
        rejected=tuple(rejected),
        errors=tuple(errors),
        queries=tuple(queries),
    )
