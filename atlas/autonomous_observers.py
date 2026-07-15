from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .autonomous import Opportunity
from .missions import list_missions
from .runner import ROOT


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def observe_recent_missions(limit: int = 20) -> list[Opportunity]:
    """Convert recent mission outcomes into improvement opportunities.

    Failed missions receive high urgency. Slow or approval-blocked missions are
    surfaced conservatively without authorising any external action.
    """

    opportunities: list[Opportunity] = []
    for mission in list_missions(limit=limit):
        mission_id = str(mission.get("mission_id", "unknown"))
        status = str(mission.get("status", "unknown"))
        latency_ms = int(mission.get("latency_ms", 0) or 0)
        revision_count = int(mission.get("revision_count", 0) or 0)

        if status == "failed":
            opportunities.append(
                Opportunity(
                    id=f"mission-failure-{mission_id}",
                    title=f"Diagnose failed mission {mission_id}",
                    impact=0.9,
                    urgency=0.95,
                    confidence=0.95,
                    effort=0.35,
                    risk=0.1,
                    metadata={"source": "mission", "mission_id": mission_id, "status": status},
                )
            )
        elif status == "approval_required":
            opportunities.append(
                Opportunity(
                    id=f"mission-approval-{mission_id}",
                    title=f"Review approval-blocked mission {mission_id}",
                    impact=0.55,
                    urgency=0.45,
                    confidence=0.9,
                    effort=0.2,
                    risk=0.2,
                    action_type="analysis",
                    metadata={"source": "mission", "mission_id": mission_id, "status": status},
                )
            )

        if latency_ms >= 10_000:
            opportunities.append(
                Opportunity(
                    id=f"mission-latency-{mission_id}",
                    title=f"Reduce latency for mission {mission_id}",
                    impact=_clamp(0.45 + latency_ms / 100_000),
                    urgency=0.5,
                    confidence=0.85,
                    effort=0.45,
                    risk=0.1,
                    metadata={"source": "mission", "mission_id": mission_id, "latency_ms": latency_ms},
                )
            )

        if revision_count >= 2:
            opportunities.append(
                Opportunity(
                    id=f"mission-quality-{mission_id}",
                    title=f"Improve first-pass quality for mission {mission_id}",
                    impact=0.65,
                    urgency=0.55,
                    confidence=0.8,
                    effort=0.4,
                    risk=0.1,
                    metadata={"source": "mission", "mission_id": mission_id, "revision_count": revision_count},
                )
            )
    return opportunities


def observe_benchmark_results(summary_path: str | Path | None = None) -> list[Opportunity]:
    path = Path(summary_path) if summary_path else ROOT / "results" / "summary.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    opportunities: list[Opportunity] = []

    failures = int(payload.get("failed", payload.get("failures", 0)) or 0)
    total = int(payload.get("total", payload.get("cases", 0)) or 0)
    pass_rate = float(payload.get("pass_rate", 1.0 if total == 0 else max(0.0, 1.0 - failures / total)))

    if failures > 0 or pass_rate < 1.0:
        opportunities.append(
            Opportunity(
                id="benchmark-regression",
                title="Investigate benchmark regression",
                impact=_clamp(1.0 - pass_rate + 0.45),
                urgency=0.9,
                confidence=0.98,
                effort=0.4,
                risk=0.1,
                metadata={"source": "benchmark", "failures": failures, "pass_rate": pass_rate},
            )
        )
    return opportunities


def observe_pull_requests(pull_requests: Iterable[dict[str, Any]]) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for pr in pull_requests:
        number = pr.get("number", pr.get("issue_number", "unknown"))
        state = str(pr.get("state", "open"))
        draft = bool(pr.get("draft", False))
        mergeable = pr.get("mergeable")
        ci = str(pr.get("ci_status", pr.get("status", "unknown"))).lower()

        if state == "open" and ci in {"failure", "failed", "error"}:
            opportunities.append(
                Opportunity(
                    id=f"pr-ci-{number}",
                    title=f"Fix failing CI on PR #{number}",
                    impact=0.85,
                    urgency=0.9,
                    confidence=0.98,
                    effort=0.35,
                    risk=0.1,
                    metadata={"source": "pull_request", "number": number, "ci_status": ci},
                )
            )
        elif state == "open" and draft:
            opportunities.append(
                Opportunity(
                    id=f"pr-draft-{number}",
                    title=f"Complete draft PR #{number}",
                    impact=0.7,
                    urgency=0.6,
                    confidence=0.9,
                    effort=0.45,
                    risk=0.1,
                    metadata={"source": "pull_request", "number": number},
                )
            )
        elif state == "open" and mergeable is False:
            opportunities.append(
                Opportunity(
                    id=f"pr-conflict-{number}",
                    title=f"Resolve conflicts on PR #{number}",
                    impact=0.75,
                    urgency=0.75,
                    confidence=0.95,
                    effort=0.3,
                    risk=0.15,
                    metadata={"source": "pull_request", "number": number},
                )
            )
    return opportunities


def observe_deployments(deployments: Iterable[dict[str, Any]]) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for deployment in deployments:
        deployment_id = str(deployment.get("id", deployment.get("run_id", "unknown")))
        status = str(deployment.get("status", deployment.get("conclusion", "unknown"))).lower()
        if status in {"failure", "failed", "error", "cancelled", "timed_out"}:
            opportunities.append(
                Opportunity(
                    id=f"deployment-{deployment_id}",
                    title=f"Diagnose failed deployment {deployment_id}",
                    impact=0.95,
                    urgency=1.0,
                    confidence=0.99,
                    effort=0.4,
                    risk=0.15,
                    metadata={"source": "deployment", "deployment_id": deployment_id, "status": status},
                )
            )
    return opportunities


def collect_observations(
    *,
    pull_requests: Iterable[dict[str, Any]] = (),
    deployments: Iterable[dict[str, Any]] = (),
    mission_limit: int = 20,
    summary_path: str | Path | None = None,
) -> list[Opportunity]:
    opportunities = []
    opportunities.extend(observe_recent_missions(limit=mission_limit))
    opportunities.extend(observe_benchmark_results(summary_path))
    opportunities.extend(observe_pull_requests(pull_requests))
    opportunities.extend(observe_deployments(deployments))
    return sorted(opportunities, key=lambda item: item.id)
