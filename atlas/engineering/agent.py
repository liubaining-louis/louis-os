from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .models import (
    BenchmarkResult,
    ChangePlan,
    CommandResult,
    EngineeringMission,
    EngineeringSummary,
    PatchResult,
    RepositoryInspection,
)


class EngineeringAgent(Protocol):
    def inspect_repository(self, mission: EngineeringMission) -> RepositoryInspection: ...

    def propose_change_plan(
        self, mission: EngineeringMission, inspection: RepositoryInspection
    ) -> ChangePlan: ...

    def generate_patch(self, mission: EngineeringMission, changes: Mapping[str, str]) -> PatchResult: ...

    def run_tests(
        self, mission: EngineeringMission, commands: Sequence[Sequence[str]] | None = None
    ) -> list[CommandResult]: ...

    def run_benchmark(self, mission: EngineeringMission) -> BenchmarkResult: ...

    def summarize_result(
        self,
        mission: EngineeringMission,
        inspection: RepositoryInspection,
        patch: PatchResult | None,
        tests: list[CommandResult],
        benchmarks: list[BenchmarkResult],
    ) -> EngineeringSummary: ...


class EngineeringEvidenceStore(Protocol):
    def append(self, mission_id: str, operation: str, payload: dict) -> Path: ...
