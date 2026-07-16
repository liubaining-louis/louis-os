from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluator import evaluate_benchmark
from .models import (
    BenchmarkResult,
    ChangePlan,
    CommandResult,
    EngineeringMission,
    EngineeringSummary,
    PatchResult,
    RepositoryInspection,
)
from .policies import PolicyViolation, redact, resolve_repository, validate_change_content, validate_target
from .sandbox import CommandRunner, LocalCommandSandbox


class JsonlEngineeringEvidenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, mission_id: str, operation: str, payload: dict) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        evidence_id = hashlib.sha256(f"{mission_id}:{operation}:{canonical}".encode()).hexdigest()[:20]
        existing_ids = set()
        if self.path.exists():
            existing_ids = {
                json.loads(line).get("evidence_id")
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        if evidence_id not in existing_ids:
            record = {
                "evidence_id": evidence_id,
                "mission_id": mission_id,
                "operation": operation,
                "payload": payload,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return self.path


class CodexEngineeringAdapter:
    """Deterministic local backend for the Codex Engineering Adapter contract.

    A future remote Codex backend can implement EngineeringAgent without changing
    Louis OS orchestration. This implementation performs no network calls.
    """

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        python_executable: str | None = None,
        evidence_store: JsonlEngineeringEvidenceStore | None = None,
    ):
        python = python_executable or os.environ.get("PYTHON", "python")
        self.python_executable = python
        self.runner = runner or LocalCommandSandbox(
            allowed_commands=(
                (python, "-m", "unittest"),
                (python, "-m", "atlas.cli", "run-all"),
                (python, "-m", "atlas.cli", "report"),
                ("git", "status"),
                ("git", "rev-parse"),
                ("git", "ls-files"),
            )
        )
        self.evidence_store = evidence_store

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        allowed_env = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed_env}
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        result = subprocess.run(
            ("git", "--no-optional-locks", *args), cwd=root, env=environment,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", shell=False, check=False, timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(redact(result.stderr.strip() or "git command failed"))
        return result.stdout.strip()

    def inspect_repository(self, mission: EngineeringMission) -> RepositoryInspection:
        root = resolve_repository(mission.repository_path)
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")
        sha = self._git(root, "rev-parse", "HEAD")
        tracked = self._git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        relevant = sorted(path for path in tracked if any(
            path == allowed.rstrip("/") or path.startswith(allowed.rstrip("/") + "/")
            for allowed in (item.replace("\\", "/") for item in mission.allowed_paths)
        ))
        porcelain = self._git(root, "status", "--porcelain")
        risks = []
        if porcelain:
            risks.append("working tree contains existing changes")
        status = "completed" if relevant else "blocked"
        inspection = RepositoryInspection(
            mission_id=mission.mission_id,
            status=status,
            current_branch=branch,
            commit_sha=sha,
            relevant_files=relevant,
            observations=[
                f"{len(tracked)} repository files",
                f"{len(relevant)} repository files within allowed paths",
                "inspection used read-only git commands",
            ],
            risks=risks,
            recommended_next_action="propose a constrained change plan" if status == "completed" else "expand the allowlist",
            evidence=[{"type": "git", "branch": branch, "commit_sha": sha, "clean": not porcelain}],
        )
        self._persist(mission.mission_id, "inspect_repository", inspection.to_dict())
        return inspection

    def propose_change_plan(
        self, mission: EngineeringMission, inspection: RepositoryInspection
    ) -> ChangePlan:
        proposed = [path for path in inspection.relevant_files if path.startswith(("tests/", "docs/", "atlas/engineering/"))]
        plan = ChangePlan(
            mission_id=mission.mission_id,
            status="completed" if inspection.status == "completed" else "blocked",
            problem=mission.objective,
            proposed_files=proposed,
            forbidden_files=[".env", ".git/", "secrets/", "iam/", ".github/workflows/deploy.yml"],
            minimal_change="make only the smallest allowlisted, reversible change that satisfies the objective",
            tests=[f"{self.python_executable} -m unittest discover -s tests -v"],
            benchmark={
                "command": f"{self.python_executable} -m atlas.cli run-all",
                "comparison": "baseline versus guarded_v1, repeated for reproducibility",
            },
            risks=inspection.risks,
            stop_conditions=[
                "working tree changes overlap the mission",
                "target path is outside the allowlist",
                "secret-like content is detected",
                "current branch is main",
                "tests or benchmark fail",
                "score, pass rate, or critical guardrail regresses",
            ],
            approval_level="none for dry-run; explicit human approval for any risky or external action",
        )
        self._persist(mission.mission_id, "propose_change_plan", plan.to_dict())
        return plan

    def generate_patch(self, mission: EngineeringMission, changes: Mapping[str, str]) -> PatchResult:
        root = resolve_repository(mission.repository_path)
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch in {"main", "master"}:
            return PatchResult(mission.mission_id, "blocked", mission.dry_run, "", [], ["direct modification on main is forbidden"])
        diffs: list[str] = []
        normalized: list[tuple[str, str]] = []
        try:
            validate_change_content(mission.objective)
            for path, content in sorted(changes.items()):
                safe_path = validate_target(path, mission.allowed_paths)
                target = (root / safe_path).resolve()
                if root not in target.parents:
                    raise PolicyViolation("resolved target escapes repository")
                old = target.read_text(encoding="utf-8") if target.exists() else ""
                validate_change_content(content, old)
                diff = difflib.unified_diff(
                    old.splitlines(keepends=True), content.splitlines(keepends=True),
                    fromfile=f"a/{safe_path}", tofile=f"b/{safe_path}",
                )
                diffs.extend(diff)
                normalized.append((safe_path, content))
        except PolicyViolation as exc:
            status = "approval_required" if exc.approval_required else "blocked"
            return PatchResult(mission.mission_id, status, mission.dry_run, "", [], [exc.reason])
        if not mission.dry_run:
            for safe_path, content in normalized:
                target = root / safe_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        result = PatchResult(
            mission_id=mission.mission_id,
            status="completed",
            dry_run=mission.dry_run,
            diff="".join(diffs),
            files_changed=[path for path, _ in normalized],
            evidence=[{"type": "patch", "applied": not mission.dry_run, "branch": branch}],
        )
        self._persist(mission.mission_id, "generate_patch", result.to_dict())
        return result

    def run_tests(
        self, mission: EngineeringMission, commands: Sequence[Sequence[str]] | None = None
    ) -> list[CommandResult]:
        root = resolve_repository(mission.repository_path)
        selected = commands or ((self.python_executable, "-m", "unittest", "discover", "-s", "tests", "-v"),)
        results = [self.runner.run(command, root) for command in selected]
        self._persist(mission.mission_id, "run_tests", {"results": [item.to_dict() for item in results]})
        return results

    def run_benchmark(self, mission: EngineeringMission) -> BenchmarkResult:
        root = resolve_repository(mission.repository_path)
        command = (self.python_executable, "-m", "atlas.cli", "run-all")
        first = self.runner.run(command, root)
        first_summary = self._read_summary(root) if first.exit_code == 0 else {}
        second = self.runner.run(command, root)
        second_summary = self._read_summary(root) if second.exit_code == 0 else {}
        reproducible = first_summary == second_summary and bool(first_summary)
        result = evaluate_benchmark(
            " ".join(command), second_summary or first_summary, [first, second],
            reproducible=reproducible,
            evidence_complete=bool(first_summary and second_summary),
        )
        self._persist(mission.mission_id, "run_benchmark", result.to_dict())
        return result

    @staticmethod
    def _read_summary(root: Path) -> dict[str, Any]:
        path = root / "results" / "summary.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def summarize_result(
        self,
        mission: EngineeringMission,
        inspection: RepositoryInspection,
        patch: PatchResult | None,
        tests: list[CommandResult],
        benchmarks: list[BenchmarkResult],
    ) -> EngineeringSummary:
        blockers = [item for benchmark in benchmarks for item in benchmark.blockers]
        if not tests:
            blockers.append("test evidence is missing")
        if not benchmarks:
            blockers.append("benchmark evidence is missing")
        blockers.extend(f"test failed: {test.command}" for test in tests if test.exit_code != 0)
        if patch and patch.status in {"blocked", "approval_required", "failed"}:
            blockers.extend(patch.risks)
        approval_required = bool(patch and patch.status == "approval_required")
        regression = any(item.regression_detected for item in benchmarks)
        status = "approval_required" if approval_required else ("blocked" if blockers or regression else "validation")
        summary = EngineeringSummary(
            mission_id=mission.mission_id,
            status=status,
            objective=mission.objective,
            files_inspected=inspection.relevant_files,
            files_changed=patch.files_changed if patch else [],
            tests=[item.to_dict() for item in tests],
            benchmarks=[item.to_dict() for item in benchmarks],
            regression_detected=regression,
            approval_required=approval_required,
            blockers=blockers,
            evidence=inspection.evidence + (patch.evidence if patch else []),
            recommended_next_action="request human approval" if approval_required else (
                "resolve the first blocker" if blockers else "submit a draft pull request for CI validation"
            ),
        )
        self._persist(mission.mission_id, "summarize_result", summary.to_dict())
        return summary

    def _persist(self, mission_id: str, operation: str, payload: dict) -> None:
        if self.evidence_store is not None:
            self.evidence_store.append(mission_id, operation, payload)
