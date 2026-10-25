"""Bounded, standalone contact CSV cleanup; stdlib only, no external action."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any

REQUIRED = ("name", "email", "company")
MAX_INPUT_BYTES = 10_000_000
MAX_ROWS = 100_000
EMAIL = re.compile(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+\Z")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def clean_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """First valid email wins; conflicting duplicates are explicitly reported.

    Row references are CSV record ordinals including the header, not physical
    line numbers (a quoted field can span several physical lines).
    """
    if len(rows) > MAX_ROWS:
        raise ValueError("row_limit_exceeded")
    output: list[dict[str, str]] = []
    seen: dict[str, tuple[int, dict[str, str]]] = {}
    issues: list[dict[str, Any]] = []
    rejected = duplicates = 0
    for number, row in enumerate(rows, 2):
        if set(row) != set(REQUIRED) or any(not isinstance(row[field], str) for field in REQUIRED):
            raise ValueError("invalid_row_shape")
        item = {field: normalize_text(row[field]) for field in REQUIRED}
        item["email"] = item["email"].casefold()
        missing = [field for field in REQUIRED if not item[field]]
        formula = [field for field in REQUIRED if item[field].startswith(("=", "+", "-", "@"))]
        if missing:
            issues.append({"row": number, "reason": "missing_required_value", "fields": missing})
            rejected += 1
        elif formula:
            issues.append({"row": number, "reason": "spreadsheet_formula", "fields": formula})
            rejected += 1
        elif not EMAIL.fullmatch(item["email"]):
            issues.append({"row": number, "reason": "invalid_email"})
            rejected += 1
        elif item["email"] in seen:
            first_number, first_item = seen[item["email"]]
            issues.append({
                "row": number,
                "reason": "duplicate_email" if item == first_item else "duplicate_email_conflict",
                "duplicate_of_row": first_number,
            })
            duplicates += 1
        else:
            seen[item["email"]] = (number, item)
            output.append(item)
    output.sort(key=lambda item: (item["company"].casefold(), item["email"]))
    report = {
        "schema_version": "1.0", "input_rows": len(rows), "output_rows": len(output),
        "rejected_rows": rejected, "duplicate_rows": duplicates, "issues": issues,
    }
    return output, report


def process_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Compatibility entrypoint; file deliveries always include the full report."""
    return clean_rows(rows)[0]


def process_file(input_path: Path, output_path: Path, report_path: Path | None = None) -> int:
    input_path, output_path = Path(input_path), Path(output_path)
    report_path = Path(report_path) if report_path is not None else output_path.with_suffix(".report.json")
    paths = [input_path.resolve(), output_path.resolve(), report_path.resolve()]
    if len(set(paths)) != 3:
        raise ValueError("paths_must_differ")
    # Refuse all existing destinations, including hard links and dangling
    # symlinks. Exclusive creation below also refuses a concurrently created file.
    if any(path.exists() or path.is_symlink() for path in (output_path, report_path)):
        raise ValueError("destination_exists")
    with input_path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input_size_limit_exceeded")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as error:
        raise ValueError("unsupported_encoding_utf8_required") from error
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, [])
        headers = [normalize_text(field).casefold() for field in headers]
        if len(headers) != len(REQUIRED) or set(headers) != set(REQUIRED):
            raise ValueError("invalid_header")
        rows = []
        for values in reader:
            if not values:  # csv blank records do not contain data
                continue
            if len(values) != len(headers):
                raise ValueError("invalid_row_shape")
            rows.append(dict(zip(headers, values)))
            if len(rows) > MAX_ROWS:
                raise ValueError("row_limit_exceeded")
    except csv.Error as error:
        raise ValueError("malformed_csv") from error
    cleaned, report = clean_rows(rows)
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REQUIRED, lineterminator="\n")
    writer.writeheader()
    writer.writerows(cleaned)
    # Validate the complete input before publishing either artifact. Ordinary
    # filesystem write failures can still leave a partial pair; never overwrite
    # or silently retry those destinations.
    with output_path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())
    with report_path.open("x", encoding="utf-8", newline="") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return len(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        count = process_file(args.input, args.output, args.report)
    except (ValueError, OSError) as error:
        print(f"csv_delivery_error: {error}", file=sys.stderr)
        return 2
    print(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
