"""Candidate-registry normalization, recovery and bounded public refresh.

The monetization worker and the Cloud Run command runtime do not share a
filesystem. This module gives the runtime a deterministic recovery path:

local registry -> Firestore snapshot -> bounded public GitHub discovery.

It performs no external submission, account creation, payment, contract or KYC.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .opportunity_authenticity import assess_opportunity_authenticity
from .opportunity_readiness import assess_opportunity_readiness

DEFAULT_QUERIES = (
    'is:issue is:open (bounty OR reward) in:title,body archived:false',
    'is:issue is:open "paid" in:title label:bounty archived:false',
    'is:issue is:open (prize OR stipend) in:title,body archived:false',
    'is:issue is:open (grant OR compensation) in:title,body archived:false',
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize historical scout fields into the executor contract."""
    value = dict(candidate)
    verified = value.get("authenticity_verified")
    if verified is None:
        verified = value.get("opportunity_authenticity_verified")
    verified = verified is True

    raw_status = value.get("authenticity_status") or value.get("opportunity_authenticity_status")
    canonical_status = "verified" if verified else str(raw_status or "unverified")
    value["authenticity_verified"] = verified
    value["authenticity_status"] = canonical_status
    value.setdefault("authenticity_reasons", list(value.get("opportunity_authenticity_reasons") or []))
    value.setdefault("authenticity_evidence", list(value.get("opportunity_authenticity_evidence") or []))
    value.setdefault("requires_user_validation", not bool(value.get("external_prerequisites_cleared")))
    return value


def normalize_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload, Mapping) else None
    if not isinstance(candidates, list):
        raise ValueError("candidate_registry_missing_candidates_array")
    normalized = dict(payload)
    normalized["schema_version"] = 3
    normalized["candidates"] = [normalize_candidate(item) for item in candidates if isinstance(item, Mapping)]
    normalized["count"] = len(normalized["candidates"])
    return normalized


def registry_is_valid(payload: Any) -> bool:
    return isinstance(payload, Mapping) and isinstance(payload.get("candidates"), list)


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


def registry_is_fresh(payload: Mapping[str, Any], max_age_minutes: int = 360) -> bool:
    generated = _parse_time(payload.get("generated_at") or payload.get("synced_at"))
    if generated is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - generated).total_seconds()
    return -300 <= age_seconds <= max(1, max_age_minutes) * 60


def _candidate_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _score(item: Mapping[str, Any], verified_amount: float) -> float:
    text = f"{item.get('title', '')} {item.get('body', '')}".casefold()
    value = 20.0 + (min(40.0, verified_amount / 25.0) if verified_amount > 0 else 0.0)
    labels = {str(entry.get("name", "")).casefold() for entry in item.get("labels", []) if isinstance(entry, Mapping)}
    if "bounty" in labels or "reward" in labels:
        value += 20.0
    if int(item.get("comments", 0) or 0) < 5:
        value += 10.0
    if any(term in text for term in ("good first issue", "beginner", "documentation", "python", "api")):
        value += 10.0
    return round(max(0.0, min(value, 100.0)), 1)


def github_get(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-self-healing-candidate-registry",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("ATLAS_EXTERNAL_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def discover_public_registry(
    getter: Callable[[str], Any] | None = None,
    *,
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    max_candidates: int = 10,
) -> dict[str, Any]:
    """Run a bounded public scout and return a normalized registry."""
    getter = getter or github_get
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in queries:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 20}
        )
        try:
            payload = getter(url)
        except Exception as exc:  # network boundary
            errors.append(f"{type(exc).__name__}: {exc}")
            continue
        for item in payload.get("items", []) if isinstance(payload, Mapping) else []:
            if not isinstance(item, Mapping):
                continue
            html_url = str(item.get("html_url") or "")
            if not html_url:
                continue
            authenticity = assess_opportunity_authenticity(item)
            attractiveness = _score(item, authenticity.reward_amount if authenticity.verified else 0.0)
            readiness = assess_opportunity_readiness(item, attractiveness)
            executable = authenticity.verified and readiness.executable_now
            found[html_url] = normalize_candidate(
                {
                    "id": _candidate_id(html_url),
                    "source": "github_public_issue",
                    "title": str(item.get("title") or ""),
                    "body": str(item.get("body") or ""),
                    "url": html_url,
                    "repository_url": str(item.get("repository_url") or ""),
                    "updated_at": item.get("updated_at"),
                    "reward_hint": authenticity.reward_amount,
                    "currency": authenticity.currency,
                    "comments": int(item.get("comments", 0) or 0),
                    "score": attractiveness,
                    "execution_score": readiness.execution_score if authenticity.verified else 0.0,
                    "readiness_status": readiness.status if authenticity.verified else "gated_unverified_opportunity",
                    "external_prerequisites": list(readiness.external_prerequisites),
                    "external_prerequisite_evidence": list(readiness.evidence),
                    "external_prerequisites_cleared": executable,
                    "requires_account": "third_party_account_required" in readiness.external_prerequisites,
                    "requires_user_validation": not executable,
                    "authenticity_verified": authenticity.verified,
                    "authenticity_status": "verified" if authenticity.verified else authenticity.status,
                    "authenticity_reasons": list(authenticity.reasons),
                    "authenticity_evidence": list(authenticity.evidence),
                    "opportunity_authenticity_verified": authenticity.verified,
                    "opportunity_authenticity_status": authenticity.status,
                    "opportunity_authenticity_reasons": list(authenticity.reasons),
                    "opportunity_authenticity_evidence": list(authenticity.evidence),
                    "status": "qualified_executable" if executable else "qualified_gated",
                }
            )

    candidates = sorted(
        found.values(),
        key=lambda item: (
            item.get("authenticity_verified") is not True,
            item.get("readiness_status") != "executable_now",
            -float(item.get("execution_score", 0) or 0),
            -float(item.get("score", 0) or 0),
            str(item.get("id", "")),
        ),
    )[: max(1, max_candidates)]
    now = utc_now()
    return {
        "schema_version": 3,
        "generated_at": now,
        "count": len(candidates),
        "authenticity_verified": sum(item.get("authenticity_verified") is True for item in candidates),
        "authenticity_blocked": sum(item.get("authenticity_verified") is not True for item in candidates),
        "candidates": candidates,
        "errors": errors,
        "recovery_source": "public_github_bounded_scout",
    }


def load_firestore_registry(project_id: str | None = None) -> dict[str, Any] | None:
    from google.cloud import firestore

    project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
    client = firestore.Client(project=project_id) if project_id else firestore.Client()
    collection = os.getenv("FIRESTORE_CANDIDATE_REGISTRY_COLLECTION", "louis_candidate_registry")
    snapshot = client.collection(collection).document("current").get()
    if not snapshot.exists:
        return None
    value = snapshot.to_dict() or {}
    registry = value.get("registry", value)
    return normalize_registry(registry) if registry_is_valid(registry) else None


def persist_firestore_registry(payload: Mapping[str, Any], project_id: str | None = None) -> None:
    from google.cloud import firestore

    project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
    client = firestore.Client(project=project_id) if project_id else firestore.Client()
    collection = os.getenv("FIRESTORE_CANDIDATE_REGISTRY_COLLECTION", "louis_candidate_registry")
    client.collection(collection).document("current").set(
        {"schema_version": 1, "synced_at": utc_now(), "registry": normalize_registry(payload)}
    )


def recover_candidate_registry(
    *,
    firestore_loader: Callable[[], dict[str, Any] | None] | None = None,
    public_discoverer: Callable[[], dict[str, Any]] | None = None,
    max_age_minutes: int | None = None,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Recover a registry without human intervention and report attempted paths."""
    errors: list[str] = []
    max_age = max_age_minutes or int(os.getenv("LOUIS_CANDIDATE_MAX_AGE_MINUTES", "360"))
    firestore_loader = firestore_loader or load_firestore_registry
    public_discoverer = public_discoverer or discover_public_registry

    try:
        snapshot = firestore_loader()
        if snapshot and registry_is_fresh(snapshot, max_age):
            normalized = normalize_registry(snapshot)
            normalized["recovery_source"] = "firestore_candidate_snapshot"
            return normalized, "firestore_candidate_snapshot", errors
        if snapshot:
            errors.append("firestore_candidate_snapshot_stale")
        else:
            errors.append("firestore_candidate_snapshot_missing")
    except Exception as exc:
        errors.append(f"firestore_recovery_failed:{type(exc).__name__}:{exc}")

    try:
        refreshed = normalize_registry(public_discoverer())
        refreshed["recovery_source"] = "public_github_bounded_scout"
        try:
            persist_firestore_registry(refreshed)
        except Exception as exc:
            errors.append(f"firestore_persist_failed:{type(exc).__name__}:{exc}")
        return refreshed, "public_github_bounded_scout", errors
    except Exception as exc:
        errors.append(f"public_scout_failed:{type(exc).__name__}:{exc}")
        return None, "unavailable", errors
