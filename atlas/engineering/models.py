from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineeringMission:
    mission_id: str
    repository_path: str
    allowed_paths: list[str]
    objective: str
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryInspection:
    mission_id: str
    status: str
    current_branch: str
    commit_sha: str
    relevant_files: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChangePlan:
    mission_id: str
    status: str
    problem: str
    proposed_files: list[str]
    forbidden_files: list[str]
    minimal_change: str
    tests: list[str]
    benchmark: dict[str, Any]
    risks: list[str]
    stop_conditions: list[str]
    approval_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PatchResult:
    mission_id: str
    status: str
    dry_run: bool
    diff: str
    files_changed: list[str]
    risks: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommandResult:
    command: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    duration_seconds: float
    stdout_excerpt: str
    stderr_excerpt: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkResult:
    command: str
    status: str
    baseline: dict[str, Any]
    variant: dict[str, Any]
    score_delta: float
    pass_rate_delta: float
    regression_detected: bool
    reproducible: bool
    evidence_complete: bool
    promotion_allowed: bool
    blockers: list[str]
    runs: list[CommandResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runs"] = [run.to_dict() for run in self.runs]
        return payload


@dataclass
class EngineeringSummary:
    mission_id: str
    status: str
    objective: str
    files_inspected: list[str]
    files_changed: list[str]
    tests: list[dict[str, Any]]
    benchmarks: list[dict[str, Any]]
    regression_detected: bool
    approval_required: bool
    blockers: list[str]
    evidence: list[dict[str, Any]]
    recommended_next_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
