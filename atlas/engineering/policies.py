from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterable


FORBIDDEN_PATH_PARTS = {
    ".env",
    ".git",
    "credentials",
    "secrets",
    "iam",
    "billing",
    "payments",
}
RISKY_ACTION_TERMS = {
    "delete resource",
    "destroy",
    "drop database",
    "force push",
    "merge pull request",
    "send email",
    "deploy production",
    "disable tests",
    "disable benchmark",
    "change quality threshold",
    "iam",
    "billing",
    "payment",
    "purchase",
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|gsk)[-_][A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{12,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class PolicyViolation(ValueError):
    def __init__(self, reason: str, *, approval_required: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.approval_required = approval_required


def redact(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


def normalize_relative(path: str) -> str:
    value = path.replace("\\", "/").strip()
    candidate = PurePosixPath(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise PolicyViolation("path must be repository-relative")
    return candidate.as_posix().rstrip("/")


def is_allowed_path(path: str, allowed_paths: Iterable[str]) -> bool:
    candidate = normalize_relative(path)
    for allowed in allowed_paths:
        prefix = normalize_relative(allowed)
        if candidate == prefix or candidate.startswith(prefix + "/"):
            return True
    return False


def validate_target(path: str, allowed_paths: Iterable[str]) -> str:
    candidate = normalize_relative(path)
    parts = {part.casefold() for part in PurePosixPath(candidate).parts}
    if parts & FORBIDDEN_PATH_PARTS or any(part.endswith((".pem", ".key")) for part in parts):
        raise PolicyViolation("secret or protected path is forbidden", approval_required=True)
    if not is_allowed_path(candidate, allowed_paths):
        raise PolicyViolation("path is outside the mission allowlist")
    return candidate


def validate_change_content(content: str, previous_content: str = "") -> None:
    if contains_secret(content):
        raise PolicyViolation("secret-like content is forbidden", approval_required=True)
    previous_lines = set(previous_content.splitlines())
    added_content = "\n".join(line for line in content.splitlines() if line not in previous_lines)
    lowered = added_content.casefold()
    if any(term in lowered for term in RISKY_ACTION_TERMS):
        raise PolicyViolation("risky or destructive action requires approval", approval_required=True)


def resolve_repository(path: str) -> Path:
    root = Path(path).resolve()
    if not root.is_dir() or not (root / ".git").exists():
        raise PolicyViolation("repository_path must identify a git repository")
    return root
