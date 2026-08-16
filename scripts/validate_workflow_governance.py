#!/usr/bin/env python3
"""Keep GitHub Actions surface bounded while Louis migrates toward shared lanes."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

WORKFLOWS = Path('.github/workflows')
MAX_WORKFLOW_FILES = 115
NAME_RE = re.compile(r'^name:\s*(.+?)\s*$', re.MULTILINE)
SCHEDULE_RE = re.compile(r'^\s*schedule:\s*$', re.MULTILINE)


def main() -> int:
    files = sorted([*WORKFLOWS.glob('*.yml'), *WORKFLOWS.glob('*.yaml')])
    names: list[str] = []
    scheduled = 0
    for path in files:
        text = path.read_text(encoding='utf-8')
        match = NAME_RE.search(text)
        names.append(match.group(1).strip('"\'') if match else path.name)
        if SCHEDULE_RE.search(text):
            scheduled += 1

    duplicate_names = sorted(name for name, count in Counter(names).items() if count > 1)
    print(f'WORKFLOW_FILES={len(files)}')
    print(f'SCHEDULED_WORKFLOWS={scheduled}')
    print(f'DUPLICATE_WORKFLOW_NAMES={len(duplicate_names)}')
    if duplicate_names:
        print('DUPLICATE_NAMES=' + ','.join(duplicate_names))

    if len(files) > MAX_WORKFLOW_FILES:
        print(f'WORKFLOW_GOVERNANCE_FAIL=workflow_count_exceeds_{MAX_WORKFLOW_FILES}')
        return 1
    print(f'WORKFLOW_GOVERNANCE_BUDGET={MAX_WORKFLOW_FILES}')
    print('WORKFLOW_GOVERNANCE=pass')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
