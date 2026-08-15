"""Dependency-free JSON to CSV converter with deterministic output validation."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class TransformError(ValueError):
    """Raised when the JSON input cannot be represented as tabular CSV rows."""


def _json_cell(value: Any) -> Any:
    """Serialize nested values deterministically while preserving scalar values."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    return value


def normalize_rows(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Return normalized rows and a deterministic union-of-keys header.

    Accepted input shapes:
    - a JSON array of objects; or
    - a single JSON object (converted to one CSV row).

    Empty arrays are valid and produce an empty CSV file. Nested dict/list cell
    values are encoded as compact JSON strings.
    """
    if isinstance(payload, Mapping):
        raw_rows: Sequence[Any] = [payload]
    elif isinstance(payload, list):
        raw_rows = payload
    else:
        raise TransformError("top-level JSON must be an object or an array of objects")

    if not raw_rows:
        return [], []

    rows: list[dict[str, Any]] = []
    columns: set[str] = set()
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise TransformError(f"row {index} is not a JSON object")
        row = {str(key): _json_cell(value) for key, value in raw.items()}
        rows.append(row)
        columns.update(row)

    return rows, sorted(columns)


def write_csv(rows: list[dict[str, Any]], columns: list[str], output_path: str | Path) -> None:
    """Write rows to CSV using UTF-8 and stable column ordering."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not columns:
            return
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def validate_csv(output_path: str | Path, *, expected_rows: int, expected_columns: list[str]) -> dict[str, Any]:
    """Read the generated CSV back and verify row count plus exact header."""
    path = Path(output_path)
    if not path.exists():
        raise TransformError("CSV output was not created")

    if not expected_columns:
        if path.read_text(encoding="utf-8") != "":
            raise TransformError("empty JSON array must produce an empty CSV file")
        return {"rows": 0, "columns": [], "valid": True}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_columns = reader.fieldnames or []
        actual_rows = list(reader)

    if actual_columns != expected_columns:
        raise TransformError(f"header mismatch: expected {expected_columns}, got {actual_columns}")
    if len(actual_rows) != expected_rows:
        raise TransformError(f"row count mismatch: expected {expected_rows}, got {len(actual_rows)}")

    return {"rows": len(actual_rows), "columns": actual_columns, "valid": True}


def convert_json_to_csv(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Load JSON, convert it to CSV, validate the generated file, and return a report."""
    source = Path(input_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransformError(f"input file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise TransformError(f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}") from exc

    rows, columns = normalize_rows(payload)
    write_csv(rows, columns, output_path)
    report = validate_csv(output_path, expected_rows=len(rows), expected_columns=columns)
    report.update({"input": str(source), "output": str(Path(output_path))})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert JSON object(s) to validated CSV.")
    parser.add_argument("input", help="Path to JSON input")
    parser.add_argument("output", help="Path to CSV output")
    args = parser.parse_args()
    try:
        report = convert_json_to_csv(args.input, args.output)
    except TransformError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
