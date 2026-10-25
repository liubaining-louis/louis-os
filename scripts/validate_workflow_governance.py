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
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.MULTILINE)


def workflow_jobs(text: str) -> list[tuple[str, str]]:
    """Extract the repository's conventional two-space job mappings.

    Fail closed on unsupported shapes rather than mistaking step/heredoc text
    for a job. This validator deliberately needs no optional YAML dependency.
    """
    section = re.search(r"^jobs:\s*\n", text, re.MULTILINE)
    if not section:
        return []
    body = text[section.end():]
    boundary = re.search(r"^[^\s#]", body, re.MULTILINE)
    if boundary:
        body = body[:boundary.start()]
    if any(
        line.strip() and line.startswith("  ") and not line.startswith(("   ", "  #"))
        and not JOB_RE.fullmatch(line)
        for line in body.splitlines()
    ):
        return []
    matches = list(JOB_RE.finditer(body))
    return [
        (match.group(1), body[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(body)])
        for index, match in enumerate(matches)
    ]


def serial_execution_errors(text: str, policy: dict, *, ci: bool = False) -> list[str]:
    failures: list[str] = []
    # A caller holding this lock while waiting for its reusable child would
    # deadlock. Only runner jobs acquire the shared execution lock.
    if CONCURRENCY_RE.search(text):
        failures.append("workflow_level_concurrency_not_allowed")
    jobs = workflow_jobs(text)
    if not jobs:
        return failures + ["jobs_mapping_missing_or_unsupported"]
    expected_group = policy["execution_concurrency_group"]
    marker = policy["policy_only_commit_marker"]
    for name, body in jobs:
        prefix = f"job:{name}:"
        condition = re.search(r"^    if:\s*(.+)$", body, re.MULTILINE)
        rollout_guard = (
            "github.event_name != 'push' || "
            f"!contains(github.event.head_commit.message, '{marker}')"
        )
        if not ci and (not condition or rollout_guard not in condition.group(1)):
            failures.append(prefix + "policy_rollout_guard_missing")
        runner = re.search(r"^    runs-on:", body, re.MULTILINE)
        reusable = re.search(r"^    uses:\s*(.+)$", body, re.MULTILINE)
        if reusable and not runner:
            if not reusable.group(1).strip().startswith("./.github/workflows/"):
                failures.append(prefix + "external_reusable_not_serialized")
            if re.search(r"^    concurrency:", body, re.MULTILINE):
                failures.append(prefix + "reusable_parent_must_not_hold_lock")
            continue
        if not runner or reusable:
            failures.append(prefix + "runner_job_shape_unsupported")
            continue
        lock = re.search(r"^    concurrency:\s*\n((?:^      [^\n]*\n?)+)", body, re.MULTILINE)
        if not lock:
            failures.append(prefix + "shared_execution_lock_missing")
        else:
            block = lock.group(1)
            if not re.search(r"^      group: " + re.escape(expected_group) + r"\s*$", block, re.MULTILINE):
                failures.append(prefix + "wrong_execution_group")
            if not re.search(r"^      cancel-in-progress: false\s*$", block, re.MULTILINE):
                failures.append(prefix + "running_work_must_not_be_cancelled")
            if not re.search(r"^      queue: max\s*$", block, re.MULTILINE):
                failures.append(prefix + "bounded_queue_missing")
        if re.search(r"^    strategy:", body, re.MULTILINE):
            if not re.search(r"^      max-parallel: 1\s*$", body, re.MULTILINE):
                failures.append(prefix + "matrix_must_be_serial")
    return failures


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
        if policy.get("require_serial_execution"):
            failures.extend(
                f"{path}:{error}"
                for error in serial_execution_errors(text, policy, ci=path.name == "ci.yml")
            )
        if SCHEDULE_RE.search(text):
            crons = CRON_RE.findall(text)
            scheduled.append((path, text, crons))
            if policy["require_manual_dispatch_for_scheduled"] and not DISPATCH_RE.search(text):
                failures.append(f"{path}:scheduled_without_workflow_dispatch")
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
    if policy.get("require_serial_execution"):
        print(f"EXECUTION_CONCURRENCY_GROUP={policy['execution_concurrency_group']}")
        print("MAX_CONCURRENT_RUNNER_JOBS=1")
    if failures:
        for failure in failures:
            print(f"WORKFLOW_GOVERNANCE_FAIL={failure}")
        return 1
    print("WORKFLOW_GOVERNANCE=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
