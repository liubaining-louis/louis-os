#!/usr/bin/env python3
"""
Read-only GCP VM and Firestore heartbeat diagnostic.

This program never enables billing, starts/stops instances, modifies Firestore,
or changes IAM. It distinguishes provider billing refusal from VM state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


BILLING_DISABLED_PATTERNS = (
    re.compile(r"billing.*disabled", re.IGNORECASE),
    re.compile(r"billing.*not enabled", re.IGNORECASE),
    re.compile(r"billing account.*(?:closed|disabled|inactive)", re.IGNORECASE),
    re.compile(r"consumer.*invalid", re.IGNORECASE),
    re.compile(r"requires an active billing account", re.IGNORECASE),
)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class HeartbeatResult:
    status: str
    observed_at: str | None
    age_seconds: int | None
    detail: str | None


@dataclass(frozen=True)
class ProbeReport:
    status: str
    project: str
    instance: str
    zone: str
    vm_state: str
    vm_detail: str
    heartbeat: HeartbeatResult
    checked_at: str


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def billing_is_disabled(result: CommandResult) -> bool:
    message = f"{result.stdout}\n{result.stderr}"
    return any(pattern.search(message) for pattern in BILLING_DISABLED_PATTERNS)


def parse_json_output(result: CommandResult) -> Mapping[str, Any]:
    if result.returncode != 0:
        raise RuntimeError(
            "command failed before JSON parsing: "
            f"exit={result.returncode}; stderr={result.stderr.strip()}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command returned invalid JSON: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("command returned JSON that is not an object")

    return payload


def gcloud_access_token() -> str:
    result = run_command(("gcloud", "auth", "print-access-token"))
    if result.returncode != 0:
        raise RuntimeError(
            "unable to obtain GCP access token: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def fetch_json(url: str, access_token: str) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firestore HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Firestore connection failure: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Firestore returned invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Firestore returned JSON that is not an object")
    return payload


def firestore_value_to_python(value: Mapping[str, Any]) -> Any:
    if "timestampValue" in value:
        return value["timestampValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "nullValue" in value:
        return None
    return None


def extract_heartbeat_timestamp(document: Mapping[str, Any]) -> str | None:
    fields = document.get("fields")
    if not isinstance(fields, dict):
        return None

    for field_name in (
        "heartbeat",
        "heartbeat_at",
        "last_heartbeat",
        "lastHeartbeat",
        "updated_at",
        "updatedAt",
    ):
        value = fields.get(field_name)
        if isinstance(value, dict):
            parsed = firestore_value_to_python(value)
            if isinstance(parsed, str):
                return parsed

    return None


def parse_rfc3339(value: str) -> dt.datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def read_heartbeat(
    project: str,
    heartbeat_document: str,
    now: dt.datetime,
    stale_after_seconds: int,
) -> HeartbeatResult:
    try:
        token = gcloud_access_token()
        encoded_document = "/".join(
            urllib.parse.quote(segment, safe="") for segment in heartbeat_document.split("/")
        )
        url = (
            "https://firestore.googleapis.com/v1/"
            f"projects/{urllib.parse.quote(project, safe='')}/"
            f"databases/(default)/documents/{encoded_document}"
        )
        document = fetch_json(url, token)
        timestamp = extract_heartbeat_timestamp(document)

        if timestamp is None:
            return HeartbeatResult(
                status="UNKNOWN",
                observed_at=None,
                age_seconds=None,
                detail="Firestore document was readable but contains no recognised heartbeat field.",
            )

        observed = parse_rfc3339(timestamp)
        age_seconds = max(0, int((now - observed).total_seconds()))
        status = "STALE" if age_seconds > stale_after_seconds else "FRESH"

        return HeartbeatResult(
            status=status,
            observed_at=observed.isoformat().replace("+00:00", "Z"),
            age_seconds=age_seconds,
            detail=(
                "Heartbeat is historical evidence only; it does not prove that "
                "the worker is currently running."
            ),
        )
    except (RuntimeError, ValueError) as exc:
        return HeartbeatResult(
            status="UNAVAILABLE",
            observed_at=None,
            age_seconds=None,
            detail=str(exc),
        )


def probe(
    project: str,
    instance: str,
    zone: str,
    heartbeat_document: str,
    stale_after_seconds: int,
) -> ProbeReport:
    now = utc_now()
    heartbeat = read_heartbeat(
        project=project,
        heartbeat_document=heartbeat_document,
        now=now,
        stale_after_seconds=stale_after_seconds,
    )

    vm_result = run_command(
        (
            "gcloud",
            "compute",
            "instances",
            "describe",
            instance,
            "--project",
            project,
            "--zone",
            zone,
            "--format=json",
        )
    )

    if billing_is_disabled(vm_result):
        return ProbeReport(
            status="BILLING_DISABLED",
            project=project,
            instance=instance,
            zone=zone,
            vm_state="UNKNOWN",
            vm_detail=(
                "Compute Engine refused the request because project billing is "
                "inactive. No conclusion about VM existence, power state, or "
                "worker health is valid from this refused request."
            ),
            heartbeat=heartbeat,
            checked_at=now.isoformat().replace("+00:00", "Z"),
        )

    if vm_result.returncode != 0:
        return ProbeReport(
            status="COMPUTE_UNAVAILABLE",
            project=project,
            instance=instance,
            zone=zone,
            vm_state="UNKNOWN",
            vm_detail=(
                "Compute Engine query failed without a billing-disabled signal: "
                f"{vm_result.stderr.strip() or vm_result.stdout.strip()}"
            ),
            heartbeat=heartbeat,
            checked_at=now.isoformat().replace("+00:00", "Z"),
        )

    try:
        instance_data = parse_json_output(vm_result)
    except RuntimeError as exc:
        return ProbeReport(
            status="COMPUTE_PROTOCOL_ERROR",
            project=project,
            instance=instance,
            zone=zone,
            vm_state="UNKNOWN",
            vm_detail=str(exc),
            heartbeat=heartbeat,
            checked_at=now.isoformat().replace("+00:00", "Z"),
        )

    vm_state = instance_data.get("status")
    if not isinstance(vm_state, str) or not vm_state:
        vm_state = "UNKNOWN"

    return ProbeReport(
        status="OK",
        project=project,
        instance=instance,
        zone=zone,
        vm_state=vm_state,
        vm_detail=(
            "Compute Engine returned instance metadata. VM state does not by "
            "itself prove application-worker health."
        ),
        heartbeat=heartbeat,
        checked_at=now.isoformat().replace("+00:00", "Z"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--zone", required=True)
    parser.add_argument("--heartbeat-document", required=True)
    parser.add_argument("--stale-after-seconds", type=int, default=900)
    args = parser.parse_args(argv)

    if args.stale_after_seconds < 1:
        parser.error("--stale-after-seconds must be greater than zero")

    report = probe(
        project=args.project,
        instance=args.instance,
        zone=args.zone,
        heartbeat_document=args.heartbeat_document,
        stale_after_seconds=args.stale_after_seconds,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0 if report.status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
