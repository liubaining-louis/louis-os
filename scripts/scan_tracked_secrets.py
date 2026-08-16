#!/usr/bin/env python3
"""Fail on obvious live-secret formats without matching the scanner itself."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

IGNORED_PREFIXES = ("tests/", "docs/", "results/")
PATTERNS = {
    "private_key": re.compile("-----BEGIN " + r"(?:RSA|EC|OPENSSH) PRIVATE KEY-----"),
    "openai_project_key": re.compile("sk-" + r"proj-[A-Za-z0-9_-]{20,}"),
    "github_pat": re.compile("ghp" + r"_[A-Za-z0-9]{30,}"),
}


def tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> int:
    findings: list[tuple[str, str]] = []
    for name in tracked_files():
        if name.startswith(IGNORED_PREFIXES):
            continue
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append((name, label))
    if findings:
        for name, label in findings:
            print(f"POTENTIAL_LIVE_SECRET {label} {name}")
        return 1
    print("TRACKED_SECRET_SCAN=clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
