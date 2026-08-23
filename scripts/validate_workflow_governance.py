#!/usr/bin/env python3
"""Enforce a bounded, event-first GitHub Actions execution surface."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

WORKFLOWS = Path(".github/workflows")
POLICY_PATH = Path("config/workflow_governance.json")
NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
SCHEDULE_RE = re.compile(r"^\s{2}schedule:\s*$", re.MULTILINE)
CRON_RE = re.compile(r"""cron:\s*['"]([^'"]+)['"]""")
DISPATCH_RE = re.compile(r"^\s{2}workflow_dispatch:\s*$", re.MULTILINE)
CONCURRENCY_RE = re.compile(r"^concurrency:\s*$", re.MULTILINE)
CANCEL_RE = re.compile(r"^\s{2}cancel-in-progress:\s*true\s*$", re.MULTILINE)


def _field_count(field: str, size: int) -> int:
    if field == "*":
        return size
    if field.startswith("*/"):
        step = int(field[2:])
        return (size + step - 1) // step
    values: set[int] = set()
    for part in field.split(","):
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            values.update(range(start, end + 1))
        else:
            values.add(int(part))
    return len(values)


def _runs_per_day(cron: str) -> int:
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"invalid_cron:{cron}")
    minute, hour, day_of_month, month, day_of_week = fields
    if (day_of_month, month, day_of_week) != ("*", "*", "*"):
        raise ValueError(f"unsupported_non_daily_cron:{cron}")
    return _field_count(minute, 60) * _field_count(hour, 24)


def _minimum_interval_minutes(cron: str) -> int:
    minute, hour, *_ = cron.split()
    if minute == "*":
        return 1
    if minute.startswith("*/"):
        return int(minute[2:])
    if hour == "*":
        return 60
    if hour.startswith("*/"):
        return 60 * int(hour[2:])
    hours = sorted(
        int(value)
        for part in hour.split(",")
        for value in (
            range(int(part.split("-", 1)[0]), int(part.split("-", 1)[1]) + 1)
            if "-" in part
            else [part]
        )
    )
    if len(hours) <= 1:
        return 24 * 60
    gaps = [b - a for a, b in zip(hours, hours[1:])]
    gaps.append(24 - hours[-1] + hours[0])
    return 60 * min(gaps)


def main() -> int:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    names: list[str] = []
    scheduled: list[tuple[Path, str, list[str]]] = []
    failures: list[str] = []

    for path in files:
        text = path.read_text(encoding="utf-8")
        match = NAME_RE.search(text)
        names.append(match.group(1).strip("\"'") if match else path.name)
        if SCHEDULE_RE.search(text):
            crons = CRON_RE.findall(text)
            scheduled.append((path, text, crons))
            if policy["require_manual_dispatch_for_scheduled"] and not DISPATCH_RE.search(text):
                failures.append(f"{path}:scheduled_without_workflow_dispatch")
            if policy["require_cancel_in_progress"]:
                if not CONCURRENCY_RE.search(text) or not CANCEL_RE.search(text):
                    failures.append(f"{path}:scheduled_without_cancel_in_progress")
            for cron in crons:
                try:
                    interval = _minimum_interval_minutes(cron)
                    if interval < policy["min_schedule_interval_minutes"]:
                        failures.append(f"{path}:interval_{interval}m_below_budget")
                except (TypeError, ValueError) as exc:
                    failures.append(f"{path}:{exc}")

    duplicate_names = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicate_names:
        failures.append("duplicate_workflow_names:" + ",".join(duplicate_names))
    if len(files) > policy["max_workflow_files"]:
        failures.append(f"workflow_count_{len(files)}_exceeds_{policy['max_workflow_files']}")
    if len(scheduled) > policy["max_scheduled_workflows"]:
        failures.append(
            f"scheduled_workflow_count_{len(scheduled)}_exceeds_{policy['max_scheduled_workflows']}"
        )

    scheduled_runs_per_day = 0
    for path, _, crons in scheduled:
        for cron in crons:
            try:
                scheduled_runs_per_day += _runs_per_day(cron)
            except (TypeError, ValueError) as exc:
                failures.append(f"{path}:{exc}")
    if scheduled_runs_per_day > policy["max_scheduled_runs_per_day"]:
        failures.append(
            f"scheduled_runs_{scheduled_runs_per_day}_exceeds_{policy['max_scheduled_runs_per_day']}"
        )

    print(f"WORKFLOW_FILES={len(files)}")
    print(f"SCHEDULED_WORKFLOWS={len(scheduled)}")
    print(f"SCHEDULED_RUNS_PER_DAY={scheduled_runs_per_day}")
    print(f"DUPLICATE_WORKFLOW_NAMES={len(duplicate_names)}")
    if failures:
        for failure in failures:
            print(f"WORKFLOW_GOVERNANCE_FAIL={failure}")
        return 1
    print("WORKFLOW_GOVERNANCE=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
