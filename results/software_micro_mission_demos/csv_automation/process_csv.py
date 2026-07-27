"""Normalize and deduplicate a contact CSV without modifying the input file."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REQUIRED = ("name", "email", "company")


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def process_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        missing = [field for field in REQUIRED if field not in row]
        if missing:
            raise ValueError("missing fields: " + ",".join(missing))
        email = normalize_text(row["email"]).casefold()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        output.append({
            "name": normalize_text(row["name"]),
            "email": email,
            "company": normalize_text(row["company"]),
        })
    return sorted(output, key=lambda item: (item["company"].casefold(), item["email"]))


def process_file(input_path: Path, output_path: Path) -> int:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("output path must differ from input path")
    with input_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    cleaned = process_rows(rows)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED)
        writer.writeheader()
        writer.writerows(cleaned)
    return len(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(process_file(args.input, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
