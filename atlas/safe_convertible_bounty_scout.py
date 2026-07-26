"""Safe, conversion-oriented discovery for autonomous GitHub bounty execution.

Provider funding evidence is necessary but not sufficient. This layer rejects prompt
exfiltration, engagement manipulation, recursive bounty farms and overcrowded tasks.
Only tasks already supported by the deterministic patch builder are marked executable;
other credible tasks remain visible in a backlog without blocking the execution queue.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

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

SAFE_QUERIES = (
    'is:issue is:open commenter:algora-pbc (typo OR documentation OR README OR "broken link") archived:false',
    'is:issue is:open label:"💎 Bounty" (typo OR documentation OR README OR "broken link") archived:false',
    'is:issue is:open label:"💎 Bounty" (replace OR rename) in:title,body archived:false',
    'is:issue is:open label:bounty "good first issue" (docs OR typo OR README) archived:false',
    'is:issue is:open in:comments "/attempt #" "Receive payment" (typo OR docs OR README) archived:false',
    'is:issue is:open in:comments "/claim #" "bounty" (typo OR documentation) archived:false',
)

_UNSAFE_TASK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_or_configuration_exfiltration",
        re.compile(
            r"system[_ ]prompt|full (?:configuration|config) prompt|paste (?:the )?complete configuration|"
            r"hidden instructions|developer message|chain[- ]of[- ]thought|internal prompt|session prompt",
            re.I,
        ),
    ),
    (
        "credential_or_secret_disclosure",
        re.compile(
            r"(?:paste|provide|include|reveal).{0,80}(?:api key|secret|token|credential|password|private key)",
            re.I | re.S,
        ),
    ),
    (
        "engagement_manipulation_required",
        re.compile(r"\b(?:star|follow|watch) the repository\b|\brepository must be starred\b", re.I),
    ),
    (
        "recursive_issue_generation_scheme",
        re.compile(
            r"issue focused on creating more issues|create (?:a|another) github issue.{0,160}(?:same contents|creator)|"
            r"only the issue author can attempt|limited only to the creator",
            re.I | re.S,
        ),
    ),
    (
        "identity_or_personal_data_request",
        re.compile(
            r"(?:add|register) yourself.{0,160}(?:identity|audit|registry)|"
            r"complete contributor identity|personal identification",
            re.I | re.S,
        ),
    ),
)

_UNSUPPORTED_CREATIVE_RE = re.compile(
    r"\b(pixel art|poem|creative writing|logo design|illustration|generate an image|original artwork)\b",
    re.I,
)
_SUSPICIOUS_REPOSITORY_RE = re.compile(
    r"(?:^|[-_/])(bounty[-_ ]?hunters?|bug[-_ ]?bounty|agent[-_ ]?playground)(?:$|[-_/])",
    re.I,
)


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def repository_trust(repo: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    score = 10.0
    owner = repo.get("owner") if isinstance(repo.get("owner"), Mapping) else {}
    if str(owner.get("type") or "").casefold() == "organization":
        score += 20.0
    stars = int(repo.get("stargazers_count", 0) or 0)
    forks = int(repo.get("forks_count", 0) or 0)
    if stars >= 100:
        score += 25.0
    elif stars >= 10:
        score += 15.0
    elif stars >= 3:
        score += 5.0
    if forks >= 10:
        score += 15.0
    elif forks >= 3:
        score += 8.0
    created = _parse_time(repo.get("created_at"))
    age_days = (now - created).days if created else None
    if age_days is not None and age_days >= 365:
        score += 15.0
    elif age_days is not None and age_days >= 90:
        score += 8.0
    pushed = _parse_time(repo.get("pushed_at"))
    push_age_days = (now - pushed).days if pushed else None
    if push_age_days is not None and push_age_days <= 30:
        score += 10.0
    elif push_age_days is not None and push_age_days <= 180:
        score += 5.0
    if str(repo.get("description") or "").strip():
        score += 5.0
    full_name = str(repo.get("full_name") or "")
    suspicious_name = bool(_SUSPICIOUS_REPOSITORY_RE.search(full_name))
    if suspicious_name:
        score -= 45.0
    return round(max(0.0, min(100.0, score)), 1), {
        "stars": stars,
        "forks": forks,
        "owner_type": str(owner.get("type") or "unknown"),
        "age_days": age_days,
        "push_age_days": push_age_days,
        "suspicious_repository_name": suspicious_name,
    }


def assess_task_safety(issue: Mapping[str, Any]) -> tuple[bool, list[str], list[str]]:
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
    reasons: list[str] = []
    evidence: list[str] = []
    for code, pattern in _UNSAFE_TASK_PATTERNS:
        match = pattern.search(text)
        if match:
            reasons.append(code)
            evidence.append(match.group(0).strip()[:240])
    return not reasons, list(dict.fromkeys(reasons)), list(dict.fromkeys(evidence))


def _round_robin(groups: Sequence[Sequence[Mapping[str, Any]]], limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = 0
    while len(output) < limit:
        advanced = False
        for group in groups:
            if index >= len(group):
                continue
            advanced = True
            item = group[index]
            url = str(item.get("html_url") or "")
            if url and url not in seen and not item.get("pull_request"):
                seen.add(url)
                output.append(dict(item))
                if len(output) >= limit:
                    break
        if not advanced:
            break
        index += 1
    return output


def _search_pool(getter: JsonGetter, queries: Sequence[str], max_inspected: int) -> tuple[list[dict[str, Any]], list[str]]:
    import urllib.parse

    groups: list[list[Mapping[str, Any]]] = []
    errors: list[str] = []
    for query in queries:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 50}
        )
        try:
            payload = getter(url)
        except Exception as exc:
            errors.append(f"search_failed:{query}:{type(exc).__name__}:{exc}")
            groups.append([])
            continue
        items = payload.get("items", []) if isinstance(payload, Mapping) else []
        groups.append([item for item in items if isinstance(item, Mapping)])
    return _round_robin(groups, max_inspected), errors


def discover_safe_convertible_registry(
    getter: JsonGetter | None = None,
    *,
    queries: Sequence[str] = SAFE_QUERIES,
    max_candidates: int = 10,
    max_inspected: int = 80,
    min_narrowness: float = 45.0,
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
            repo_url = _repo_url(issue)
            if repo_url not in repo_cache:
                repo_payload = getter(repo_url)
                repo_cache[repo_url] = dict(repo_payload) if isinstance(repo_payload, Mapping) else {}
            repo = repo_cache[repo_url]

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

            candidate, rejection = _qualify_issue(issue, comments, repo, min_narrowness=min_narrowness)
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

            text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
            creative_only = bool(_UNSUPPORTED_CREATIVE_RE.search(text))
            handler = str(candidate.get("patch_handler") or "")
            convertible = handler == "deterministic_text_replacement" and not creative_only
            candidate.update(
                {
                    "task_safety_status": "safe",
                    "task_safety_reasons": [],
                    "repository_trust_score": trust_score,
                    "repository_trust_evidence": trust_evidence,
                    "current_patch_handler_supported": convertible,
                    "conversion_probability": round(
                        max(
                            0.0,
                            min(
                                100.0,
                                float(candidate.get("narrowness_score", 0) or 0) * 0.45
                                + trust_score * 0.35
                                + max(0.0, 20.0 - attempts * 4.0),
                            ),
                        ),
                        1,
                    ),
                }
            )
            if convertible:
                candidate["readiness_status"] = "executable_now"
                candidate["external_prerequisites"] = []
                candidate["external_prerequisites_cleared"] = True
                candidate["requires_user_validation"] = False
                candidate["status"] = "qualified_executable"
                qualified.append(candidate)
            else:
                candidate["readiness_status"] = "gated_unsupported_patch_handler"
                candidate["external_prerequisites"] = ["bounded_patch_handler_not_implemented"]
                candidate["external_prerequisites_cleared"] = False
                candidate["requires_user_validation"] = False
                candidate["status"] = "credible_backlog_not_executable"
                candidate["backlog_reason"] = (
                    "unsupported_creative_deliverable" if creative_only else "bounded_patch_handler_not_implemented"
                )
                backlog.append(candidate)
        except Exception as exc:
            rejected.append(
                {
                    **rejection_base,
                    "reason": "qualification_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    qualified.sort(
        key=lambda item: (
            -float(item.get("conversion_probability", 0) or 0),
            -float(item.get("reward_scope_ratio", 0) or 0),
            str(item.get("id", "")),
        )
    )
    backlog.sort(
        key=lambda item: (
            -float(item.get("conversion_probability", 0) or 0),
            -float(item.get("reward_scope_ratio", 0) or 0),
            str(item.get("id", "")),
        )
    )

    def cap_by_repository(items: Sequence[dict[str, Any]], total: int) -> list[dict[str, Any]]:
        counts: defaultdict[str, int] = defaultdict(int)
        selected: list[dict[str, Any]] = []
        for item in items:
            repo = str(item.get("target_repository") or "unknown")
            if counts[repo] >= max_candidates_per_repository:
                continue
            counts[repo] += 1
            selected.append(item)
            if len(selected) >= total:
                break
        return selected

    candidates = cap_by_repository(qualified, max_candidates)
    credible_backlog = cap_by_repository(backlog, max_candidates)
    registry = {
        "schema_version": 5,
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
        "recovery_source": "safe_convertible_platform_backed_github_scout",
        "root_cause_code": None if candidates else "no_safe_convertible_payable_candidate",
    }
    return ScoutOutcome(
        registry=registry,
        inspected=len(pool),
        qualified=len(candidates),
        rejected=tuple(rejected),
        errors=tuple(errors),
        queries=tuple(queries),
    )
