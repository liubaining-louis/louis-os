"""Self-healing wrapper for the deterministic monetization execution cycle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .candidate_registry import normalize_registry, recover_candidate_registry, registry_is_valid
from .monetization_execution_cycle import run_verified_deliverable_cycle as run_once
from .runner import ROOT


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def run_self_healing_deliverable_cycle(
    root: Path | None = None,
    *,
    recoverer: Callable[[], tuple[dict[str, Any] | None, str, list[str]]] | None = None,
    enable_external_recovery: bool | None = None,
) -> dict[str, Any]:
    """Repair candidate state, retry immediately, and preserve causal evidence.

    External recovery means read-only Firestore retrieval and bounded public
    GitHub search. It never posts, claims, creates accounts or accepts terms.
    """
    repository_root = (root or ROOT).resolve()
    results = repository_root / "results"
    candidates_path = results / "monetization_candidates.json"
    recovery_path = results / "candidate_registry_recovery.json"
    payload = _load_json(candidates_path)

    # Production defaults to recovery. Temporary test roots remain offline unless
    # a recoverer is explicitly injected.
    if enable_external_recovery is None:
        enable_external_recovery = recoverer is not None or repository_root == ROOT.resolve()

    recovery: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempted": False,
        "source": "local_candidate_registry",
        "errors": [],
        "registry_repaired": False,
        "automatic_retry": False,
    }

    if registry_is_valid(payload):
        normalized = normalize_registry(payload)
        if normalized != payload:
            _write_json(candidates_path, normalized)
            recovery.update(
                {
                    "attempted": True,
                    "source": "local_schema_normalization",
                    "registry_repaired": True,
                    "automatic_retry": True,
                }
            )
            _write_json(recovery_path, recovery)
    elif enable_external_recovery:
        recovery["attempted"] = True
        recovery_fn = recoverer or recover_candidate_registry
        registry, source, errors = recovery_fn()
        recovery.update({"source": source, "errors": errors})
        if registry_is_valid(registry):
            normalized = normalize_registry(registry or {})
            _write_json(candidates_path, normalized)
            recovery.update({"registry_repaired": True, "automatic_retry": True})
        _write_json(recovery_path, recovery)

    outcome = run_once(repository_root)
    if recovery["attempted"]:
        evidence = list(outcome.get("evidence") or [])
        if recovery_path.is_file():
            evidence.append(recovery_path.relative_to(repository_root).as_posix())
        outcome["evidence"] = list(dict.fromkeys(evidence))
        outcome["candidate_registry_recovery"] = recovery

    # A syntactically valid historical registry can still contain only legacy or
    # unusable candidates. Force one bounded refresh, then retry in the same call.
    retry_reasons = {
        "candidate_file_unavailable",
        "no_authentic_executable_candidate",
        "no_qualified_opportunity",
        "all_opportunities_gated",
    }
    if (
        enable_external_recovery
        and outcome.get("status") == "blocked"
        and outcome.get("reason") in retry_reasons
        and recovery.get("source") == "local_candidate_registry"
    ):
        recovery_fn = recoverer or recover_candidate_registry
        registry, source, errors = recovery_fn()
        recovery.update(
            {
                "attempted": True,
                "source": source,
                "errors": errors,
                "automatic_retry": True,
                "registry_repaired": registry_is_valid(registry),
            }
        )
        if registry_is_valid(registry):
            _write_json(candidates_path, normalize_registry(registry or {}))
        _write_json(recovery_path, recovery)
        retried = run_once(repository_root)
        evidence = list(retried.get("evidence") or [])
        evidence.append(recovery_path.relative_to(repository_root).as_posix())
        retried["evidence"] = list(dict.fromkeys(evidence))
        retried["candidate_registry_recovery"] = recovery
        retried["automatic_retry_performed"] = True
        return retried

    outcome["automatic_retry_performed"] = bool(recovery.get("automatic_retry"))
    return outcome
