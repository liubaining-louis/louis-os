"""Discovery of genuine, narrow and platform-backed GitHub bounty opportunities.

The scout is intentionally fail-closed. It does not trust arbitrary money text in
issue bodies. A candidate qualifies only when a recognized bounty provider bot
publishes objective reward evidence and the target remains open, available and
small enough to be a realistic autonomous patch candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

JsonGetter = Callable[[str], Any]

DEFAULT_QUERIES = (
    'is:issue is:open label:"💎 Bounty" -label:"💰 Rewarded" archived:false',
    'is:issue is:open label:bounty "good first issue" archived:false',
    'is:issue is:open in:comments "/attempt #" "Receive payment" archived:false',
    'is:issue is:open in:comments "/claim #" "bounty" archived:false',
)

_MONEY_RE = re.compile(
    r"(?:([$€£])\s*([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(USD|EUR|GBP))",
    re.I,
)
_ALGORA_RE = re.compile(r"##\s*💎.*?\bbounty\b", re.I | re.S)
_OPIRE_RE = re.compile(r"\bopire\b.*?\b(?:reward|bounty)\b", re.I | re.S)
_EXACT_REPLACEMENT_RE = re.compile(
    r"(?:replace|change|fix|rename)\s*[`'\"]([^`'\"\n]{1,200})[`'\"]\s*(?:with|to)\s*[`'\"]([^`'\"\n]{1,200})[`'\"]",
    re.I,
)
_FILE_RE = re.compile(
    r"(?:\bfile\b|\bin\b)\s*[:：]?\s*[`'\"]?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]+)[`'\"]?",
    re.I,
)
_UNAVAILABLE_RE = re.compile(
    r"winner selected|bounty (?:is )?(?:closed|cancelled|canceled|withdrawn)|"
    r"refrain from submitting|finali[sz]ed for this bounty|pending app review|"
    r"already (?:claimed|assigned)|no longer available",
    re.I,
)
_BROAD_RE = re.compile(
    r"\b(full implementation|implement in full|all main|entire codebase|"
    r"large refactor|rewrite|migration|architecture overhaul|20[,.]?000 lines|"
    r"100\+? files|spritework|mapping work)\b",
    re.I,
)
_NARROW_LABELS = {
    "good first issue",
    "documentation",
    "docs",
    "typo",
    "small",
    "size:s",
    "size/xs",
    "easy",
    "beginner",
}
_DOC_TERMS = re.compile(r"\b(docs?|documentation|typo|spelling|broken link|readme|example)\b", re.I)
_ATTEMPT_RE = re.compile(r"/attempt\s+#?\d+", re.I)
_STRUCK_BOUNTY_RE = re.compile(r"~~\s*##\s*💎", re.I)


@dataclass(frozen=True)
class ProviderEvidence:
    provider: str
    reward_amount: float
    currency: str
    comment_url: str
    comment_author: str
    evidence_excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoutOutcome:
    registry: dict[str, Any]
    inspected: int
    qualified: int
    rejected: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    queries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def github_get_json(url: str) -> Any:
    token = os.getenv("ATLAS_EXTERNAL_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-narrow-payable-scout",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _candidate_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _labels(issue: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    raw = issue.get("labels")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip().casefold()
            else:
                name = str(item).strip().casefold()
            if name:
                values.add(name)
    return values


def _currency(symbol: str | None, code: str | None) -> str:
    if code:
        return code.upper()
    return {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol or "", "unknown")


def _money(text: str) -> tuple[float, str] | None:
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    raw = (match.group(2) or match.group(3) or "0").replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None
    if amount <= 0:
        return None
    return amount, _currency(match.group(1), match.group(4))


def detect_provider_evidence(comments: Sequence[Mapping[str, Any]]) -> ProviderEvidence | None:
    """Return objective provider evidence from a recognized bot comment."""
    for comment in comments:
        user = comment.get("user") if isinstance(comment.get("user"), Mapping) else {}
        login = str(user.get("login") or "").casefold()
        normalized = login.removesuffix("[bot]")
        body = str(comment.get("body") or "")
        if _STRUCK_BOUNTY_RE.search(body):
            continue
        provider = ""
        valid = False
        if normalized == "algora-pbc":
            provider = "algora"
            valid = bool(_ALGORA_RE.search(body) and "/attempt" in body and "/claim" in body)
        elif "opire" in normalized:
            provider = "opire"
            valid = bool(_OPIRE_RE.search(body) and re.search(r"\bclaim\b", body, re.I))
        if not valid:
            continue
        reward = _money(body)
        if reward is None:
            continue
        amount, currency = reward
        return ProviderEvidence(
            provider=provider,
            reward_amount=amount,
            currency=currency,
            comment_url=str(comment.get("html_url") or ""),
            comment_author=login,
            evidence_excerpt=re.sub(r"\s+", " ", body).strip()[:320],
        )
    return None


def _repository_full_name(issue: Mapping[str, Any]) -> str:
    repository_url = str(issue.get("repository_url") or "")
    parts = [part for part in urllib.parse.urlparse(repository_url).path.split("/") if part]
    if len(parts) >= 3 and parts[-3] == "repos":
        return f"{parts[-2]}/{parts[-1]}"
    html_url = str(issue.get("html_url") or "")
    html_parts = [part for part in urllib.parse.urlparse(html_url).path.split("/") if part]
    if len(html_parts) >= 2:
        return f"{html_parts[0]}/{html_parts[1]}"
    raise ValueError("repository_identity_unavailable")


def _comments_url(issue: Mapping[str, Any]) -> str:
    direct = str(issue.get("comments_url") or "")
    if direct:
        separator = "&" if "?" in direct else "?"
        return f"{direct}{separator}per_page=100"
    full_name = _repository_full_name(issue)
    number = int(issue.get("number") or 0)
    if number <= 0:
        raise ValueError("issue_number_unavailable")
    return f"https://api.github.com/repos/{full_name}/issues/{number}/comments?per_page=100"


def _repo_url(issue: Mapping[str, Any]) -> str:
    direct = str(issue.get("repository_url") or "")
    return direct or f"https://api.github.com/repos/{_repository_full_name(issue)}"


def _active_attempts(comments: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for comment in comments:
        user = comment.get("user") if isinstance(comment.get("user"), Mapping) else {}
        login = str(user.get("login") or "").casefold()
        if "algora" in login or "opire" in login:
            continue
        body = str(comment.get("body") or "")
        if _ATTEMPT_RE.search(body) and not re.search(r"\bcancel(?:led)?\b", body, re.I):
            count += 1
    return count


def _file_paths(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in _FILE_RE.finditer(text or "")))


def _requirement_count(text: str) -> int:
    lines = (text or "").splitlines()
    bullets = sum(bool(re.match(r"\s*(?:[-*]|\d+[.)])\s+\S", line)) for line in lines)
    headings = len(re.findall(r"\brequirements?\b|\bacceptance criteria\b", text or "", re.I))
    return bullets + headings


def score_narrowness(issue: Mapping[str, Any]) -> tuple[float, str, dict[str, Any]]:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    text = f"{title}\n{body}"
    labels = _labels(issue)
    paths = _file_paths(text)
    requirements = _requirement_count(body)
    broad_hits = len(_BROAD_RE.findall(text))
    exact_replacement = bool(_EXACT_REPLACEMENT_RE.search(text) and paths)

    score = 25.0
    if labels.intersection(_NARROW_LABELS):
        score += 25.0
    if _DOC_TERMS.search(text):
        score += 20.0
    if 1 <= len(paths) <= 3:
        score += 15.0
    if exact_replacement:
        score += 20.0
    if len(body) <= 2500:
        score += 5.0
    score -= min(30.0, broad_hits * 20.0)
    score -= min(20.0, max(0, requirements - 6) * 2.5)
    if len(paths) > 5:
        score -= min(20.0, (len(paths) - 5) * 3.0)
    score = round(max(0.0, min(100.0, score)), 1)

    if exact_replacement:
        handler = "deterministic_text_replacement"
    elif _DOC_TERMS.search(text) and 1 <= len(paths) <= 3:
        handler = "bounded_documentation_patch"
    elif labels.intersection(_NARROW_LABELS) and requirements <= 8:
        handler = "bounded_small_task"
    else:
        handler = "unsupported_without_new_handler"
    return score, handler, {
        "file_paths": paths,
        "requirements": requirements,
        "broad_hits": broad_hits,
        "body_length": len(body),
        "exact_replacement": exact_replacement,
    }


def _unavailable_reason(issue: Mapping[str, Any], comments: Sequence[Mapping[str, Any]]) -> str | None:
    if str(issue.get("state") or "open").casefold() != "open":
        return "issue_not_open"
    labels = _labels(issue)
    if "💰 rewarded" in labels or "rewarded" in labels:
        return "already_rewarded"
    combined = "\n".join(
        [str(issue.get("title") or ""), str(issue.get("body") or "")]
        + [str(comment.get("body") or "") for comment in comments]
    )
    if _STRUCK_BOUNTY_RE.search(combined):
        return "provider_bounty_struck_or_cancelled"
    if _UNAVAILABLE_RE.search(combined):
        return "explicitly_unavailable_or_reserved"
    return None


def _qualify_issue(
    issue: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
    repo: Mapping[str, Any],
    *,
    min_narrowness: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = str(issue.get("html_url") or "")
    candidate_id = _candidate_id(url) if url else "unknown"
    rejected: dict[str, Any] = {"candidate_id": candidate_id, "url": url, "title": str(issue.get("title") or "")}

    unavailable = _unavailable_reason(issue, comments)
    if unavailable:
        rejected.update({"reason": unavailable})
        return None, rejected
    if repo.get("archived") is True or repo.get("disabled") is True:
        rejected.update({"reason": "repository_archived_or_disabled"})
        return None, rejected

    evidence = detect_provider_evidence(comments)
    if evidence is None:
        rejected.update({"reason": "recognized_provider_evidence_missing"})
        return None, rejected

    narrowness, handler, scope = score_narrowness(issue)
    if narrowness < min_narrowness:
        rejected.update({"reason": "task_not_narrow_enough", "narrowness_score": narrowness, "scope": scope})
        return None, rejected

    attempts = _active_attempts(comments)
    assignees = issue.get("assignees") if isinstance(issue.get("assignees"), list) else []
    competition = attempts + len(assignees)
    payability = 80.0
    if evidence.comment_url:
        payability += 10.0
    if evidence.reward_amount > 0:
        payability += 10.0
    payability = min(100.0, payability)
    effort_units = max(1.0, 1.0 + (100.0 - narrowness) / 25.0 + competition * 0.75)
    reward_scope_ratio = round(evidence.reward_amount / effort_units, 2)
    execution_score = round(
        max(
            0.0,
            min(
                100.0,
                narrowness * 0.55
                + payability * 0.35
                + min(10.0, reward_scope_ratio / 10.0)
                - min(20.0, competition * 4.0),
            ),
        ),
        1,
    )
    full_name = _repository_full_name(issue)
    labels = sorted(_labels(issue))
    candidate = {
        "id": candidate_id,
        "source": "github_platform_backed_bounty",
        "title": str(issue.get("title") or ""),
        "body": str(issue.get("body") or ""),
        "url": url,
        "canonical_issue_url": url,
        "repository_url": str(issue.get("repository_url") or ""),
        "target_repository": full_name,
        "updated_at": issue.get("updated_at"),
        "reward_hint": evidence.reward_amount,
        "reward_amount": evidence.reward_amount,
        "currency": evidence.currency,
        "payment_provider": evidence.provider,
        "provider_evidence": evidence.to_dict(),
        "credible_payable": True,
        "payability_score": payability,
        "narrowness_score": narrowness,
        "patch_handler": handler,
        "scope_evidence": scope,
        "active_attempts": attempts,
        "assignee_count": len(assignees),
        "competition_score": competition,
        "reward_scope_ratio": reward_scope_ratio,
        "labels": labels,
        "score": execution_score,
        "execution_score": execution_score,
        "readiness_status": "executable_now",
        "external_prerequisites": [],
        "external_prerequisite_evidence": [],
        "external_prerequisites_cleared": True,
        "requires_account": False,
        "requires_user_validation": False,
        "submission_capability": "existing_authorized_github_identity",
        "payout_gate_status": "deferred_until_award",
        "payout_prerequisites": ["provider payout profile or tax/KYC review may be required after award"],
        "authenticity_verified": True,
        "authenticity_status": "verified",
        "authenticity_reasons": [],
        "authenticity_evidence": [evidence.comment_url, evidence.evidence_excerpt],
        "opportunity_authenticity_verified": True,
        "opportunity_authenticity_status": "verified_platform_backed_reward",
        "opportunity_authenticity_reasons": [],
        "opportunity_authenticity_evidence": [evidence.comment_url, evidence.evidence_excerpt],
        "status": "qualified_executable",
    }
    return candidate, rejected


def discover_narrow_payable_registry(
    getter: JsonGetter | None = None,
    *,
    queries: Sequence[str] = DEFAULT_QUERIES,
    max_candidates: int = 10,
    max_inspected: int = 40,
    min_narrowness: float = 45.0,
) -> ScoutOutcome:
    getter = getter or github_get_json
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in queries:
        search_url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 20}
        )
        try:
            payload = getter(search_url)
        except Exception as exc:
            errors.append(f"search_failed:{query}:{type(exc).__name__}:{exc}")
            continue
        items = payload.get("items", []) if isinstance(payload, Mapping) else []
        for item in items:
            if not isinstance(item, Mapping) or item.get("pull_request"):
                continue
            url = str(item.get("html_url") or "")
            if url and url not in found:
                found[url] = dict(item)
            if len(found) >= max_inspected:
                break
        if len(found) >= max_inspected:
            break

    qualified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for issue in list(found.values())[:max_inspected]:
        url = str(issue.get("html_url") or "")
        try:
            comments_payload = getter(_comments_url(issue))
            comments = [dict(item) for item in comments_payload if isinstance(item, Mapping)] if isinstance(comments_payload, list) else []
            repo_payload = getter(_repo_url(issue))
            repo = dict(repo_payload) if isinstance(repo_payload, Mapping) else {}
            candidate, rejection = _qualify_issue(issue, comments, repo, min_narrowness=min_narrowness)
            if candidate is None:
                rejected.append(rejection)
            else:
                qualified.append(candidate)
        except Exception as exc:
            rejected.append(
                {
                    "candidate_id": _candidate_id(url) if url else "unknown",
                    "url": url,
                    "title": str(issue.get("title") or ""),
                    "reason": "qualification_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    qualified.sort(
        key=lambda item: (
            item.get("patch_handler") not in {"deterministic_text_replacement", "bounded_documentation_patch"},
            -float(item.get("execution_score", 0) or 0),
            -float(item.get("reward_scope_ratio", 0) or 0),
            int(item.get("competition_score", 0) or 0),
            str(item.get("id", "")),
        )
    )
    candidates = qualified[: max(1, max_candidates)]
    now = utc_now()
    registry = {
        "schema_version": 4,
        "generated_at": now,
        "count": len(candidates),
        "authenticity_verified": len(candidates),
        "authenticity_blocked": len(rejected),
        "credible_candidates": len(candidates),
        "provider_backed_candidates": len(candidates),
        "narrow_candidates": sum(float(item.get("narrowness_score", 0)) >= min_narrowness for item in candidates),
        "candidates": candidates,
        "errors": errors,
        "recovery_source": "narrow_platform_backed_github_scout",
        "root_cause_code": None if candidates else "no_genuine_narrow_payable_candidate",
    }
    return ScoutOutcome(
        registry=registry,
        inspected=len(found),
        qualified=len(candidates),
        rejected=tuple(rejected),
        errors=tuple(errors),
        queries=tuple(queries),
    )
