from __future__ import annotations

from typing import Any

from .models import BenchmarkResult, CommandResult


def evaluate_benchmark(
    command: str,
    summary: dict[str, Any],
    runs: list[CommandResult],
    *,
    reproducible: bool,
    evidence_complete: bool,
) -> BenchmarkResult:
    baseline = dict(summary.get("baseline", {}))
    variant = dict(summary.get("guarded_v1", summary.get("variant", {})))
    blockers: list[str] = []
    if not baseline or not variant or any(run.exit_code != 0 for run in runs):
        blockers.append("benchmark evidence is missing or execution failed")
        evidence_complete = False
    score_delta = float(variant.get("score", 0.0)) - float(baseline.get("score", 0.0))
    pass_rate_delta = float(variant.get("pass_rate", 0.0)) - float(baseline.get("pass_rate", 0.0))
    if score_delta < 0:
        blockers.append("mean score regressed")
    if pass_rate_delta < 0:
        blockers.append("pass rate regressed")
    if int(variant.get("critical_regressions", 0)) > 0:
        blockers.append("critical guardrail regressed")
    if not reproducible:
        blockers.append("benchmark is not reproducible")
    if not evidence_complete:
        blockers.append("benchmark evidence is incomplete")
    regression = any("regress" in blocker for blocker in blockers)
    allowed = not blockers
    return BenchmarkResult(
        command=command,
        status="completed" if allowed else "blocked",
        baseline=baseline,
        variant=variant,
        score_delta=score_delta,
        pass_rate_delta=pass_rate_delta,
        regression_detected=regression,
        reproducible=reproducible,
        evidence_complete=evidence_complete,
        promotion_allowed=allowed,
        blockers=blockers,
        runs=runs,
    )
