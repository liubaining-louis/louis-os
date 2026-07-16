from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .models import CommandResult
from .policies import PolicyViolation, redact


_TEST_COUNTS = re.compile(r"Ran\s+(\d+)\s+tests?", re.IGNORECASE)
_FAILURES = re.compile(r"failures=(\d+)", re.IGNORECASE)
_ERRORS = re.compile(r"errors=(\d+)", re.IGNORECASE)


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], cwd: Path) -> CommandResult: ...


@dataclass
class LocalCommandSandbox:
    allowed_commands: tuple[tuple[str, ...], ...]
    timeout_seconds: float = 120.0
    max_output_chars: int = 12000

    def _validate(self, command: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(str(item) for item in command)
        if not normalized or not any(normalized[: len(prefix)] == prefix for prefix in self.allowed_commands):
            raise PolicyViolation("command is not allowlisted")
        return normalized

    def _environment(self) -> dict[str, str]:
        allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}

    def run(self, command: Sequence[str], cwd: Path) -> CommandResult:
        argv = self._validate(command)
        started = time.perf_counter()
        timed_out = False
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd.resolve()),
                env=self._environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            timed_out = True
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\ncommand timed out"
        duration = round(time.perf_counter() - started, 3)
        combined = f"{stdout}\n{stderr}"
        count = int(_TEST_COUNTS.search(combined).group(1)) if _TEST_COUNTS.search(combined) else 0
        failed = int(_FAILURES.search(combined).group(1)) if _FAILURES.search(combined) else 0
        errors = int(_ERRORS.search(combined).group(1)) if _ERRORS.search(combined) else 0
        if exit_code != 0 and count and failed == 0 and errors == 0:
            errors = 1
        return CommandResult(
            command=" ".join(argv),
            exit_code=exit_code,
            passed=max(0, count - failed - errors),
            failed=failed,
            errors=errors,
            duration_seconds=duration,
            stdout_excerpt=self._safe_excerpt(stdout),
            stderr_excerpt=self._safe_excerpt(stderr),
            timed_out=timed_out,
        )

    def _safe_excerpt(self, value: str) -> str:
        safe = redact(value)
        if len(safe) <= self.max_output_chars:
            return safe
        return safe[: self.max_output_chars] + "\n[output truncated]"
