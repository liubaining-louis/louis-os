from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from atlas.csv_delivery import process_file
from atlas.software_micro_missions import csv_automation_demo_files


class CsvDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="louis-csv-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "input.csv"
        self.original = b"name,email,company\n Alice ,ALICE@example.com, Acme \n"
        self.source.write_bytes(self.original)

    def test_reviewable_delivery_packet_matches_actual_artifacts(self) -> None:
        demo = Path(__file__).resolve().parents[1] / "deliverables/csv_cleanup_demo"
        original = (demo / "input.csv").read_bytes()
        source = self.root / "demo.csv"
        source.write_bytes(original)
        output, report = self.root / "cleaned.csv", self.root / "report.json"
        self.assertEqual(process_file(source, output, report), 2)
        self.assertEqual(output.read_bytes(), (demo / "cleaned.csv").read_bytes())
        self.assertEqual(report.read_bytes(), (demo / "report.json").read_bytes())
        self.assertEqual(source.read_bytes(), original)

    def test_same_path_and_symbolic_or_hard_link_cannot_overwrite_input(self) -> None:
        for kind in ("same", "symlink", "hardlink"):
            with self.subTest(kind=kind):
                destination = self.root / kind
                if kind == "same":
                    destination = self.source
                elif kind == "symlink":
                    destination.symlink_to(self.source)
                else:
                    destination.hardlink_to(self.source)
                with self.assertRaises(ValueError):
                    process_file(self.source, destination)
                self.assertEqual(self.source.read_bytes(), self.original)

    def test_existing_output_and_report_are_never_replaced(self) -> None:
        for existing_name in ("cleaned.csv", "report.json"):
            with self.subTest(path=existing_name), tempfile.TemporaryDirectory(dir=self.root) as directory:
                target = Path(directory)
                output, report = target / "cleaned.csv", target / "report.json"
                existing = target / existing_name
                existing.write_bytes(b"KEEP THIS FILE")
                with self.assertRaisesRegex(ValueError, "destination_exists"):
                    process_file(self.source, output, report)
                self.assertEqual(existing.read_bytes(), b"KEEP THIS FILE")
                other = output if existing == report else report
                self.assertFalse(other.exists())
                self.assertEqual(self.source.read_bytes(), self.original)

    def test_report_must_differ_from_source_and_output(self) -> None:
        for path in (self.source, self.root / "cleaned.csv"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "paths_must_differ"):
                    process_file(self.source, self.root / "cleaned.csv", path)
                self.assertFalse((self.root / "cleaned.csv").exists())
                self.assertEqual(self.source.read_bytes(), self.original)

    def test_default_report_and_repeated_runs_are_deterministic(self) -> None:
        first, second = self.root / "first.csv", self.root / "second.csv"
        self.assertEqual(process_file(self.source, first), 1)
        self.assertEqual(process_file(self.source, second), 1)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.with_suffix(".report.json").read_bytes(), second.with_suffix(".report.json").read_bytes())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_encoding_and_size_limits_fail_before_publication(self) -> None:
        output = self.root / "cleaned.csv"
        self.source.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(ValueError, "unsupported_encoding"):
            process_file(self.source, output)
        self.assertFalse(output.exists())
        self.source.write_bytes(self.original)
        with patch("atlas.csv_delivery.MAX_INPUT_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "input_size_limit"):
                process_file(self.source, output)
        self.assertFalse(output.exists())

    def test_row_limit_fails_before_publication(self) -> None:
        with patch("atlas.csv_delivery.MAX_ROWS", 0):
            with self.assertRaisesRegex(ValueError, "row_limit"):
                process_file(self.source, self.root / "cleaned.csv")
        self.assertFalse((self.root / "cleaned.csv").exists())

    def test_32_generated_variants_follow_the_same_contract(self) -> None:
        generator = random.Random(20261025)
        namespace = {"__name__": "trusted_standalone_csv"}
        exec(csv_automation_demo_files()["process_csv.py"], namespace)
        for index in range(32):
            with self.subTest(variant=index), tempfile.TemporaryDirectory(dir=self.root) as directory:
                root = Path(directory)
                expected = [
                    {"name": f"Person {index}-{n}", "email": f"person{index}-{n}@example.com", "company": f"Company {generator.randrange(4)}"}
                    for n in range(generator.randrange(1, 10))
                ]
                rows = [dict(row) for row in expected]
                duplicate = dict(generator.choice(expected))
                rows.append(duplicate)
                rows.append({"name": "", "email": "missing@example.com", "company": "Company"})
                generator.shuffle(rows)
                headers = ["name", "email", "company"]
                generator.shuffle(headers)
                data = io.StringIO(newline="")
                writer = csv.writer(data, lineterminator="\r\n" if index % 2 else "\n")
                writer.writerow([" " + field.upper() + " " for field in headers])
                for row in rows:
                    writer.writerow([" " + (row[field].upper() if field == "email" else row[field]) + " " for field in headers])
                source, output, report = root / "source.csv", root / "cleaned.csv", root / "report.json"
                raw = (("\ufeff" if index % 3 == 0 else "") + data.getvalue()).encode("utf-8")
                source.write_bytes(raw)
                namespace["process_file"](source, output, report)
                with output.open(encoding="utf-8", newline="") as handle:
                    actual = list(csv.DictReader(handle))
                self.assertEqual(actual, sorted(expected, key=lambda row: (row["company"].casefold(), row["email"])))
                receipt = json.loads(report.read_text())
                self.assertEqual(receipt["input_rows"], len(expected) + 2)
                self.assertEqual(receipt["output_rows"], len(expected))
                self.assertEqual(receipt["rejected_rows"], 1)
                self.assertEqual(receipt["duplicate_rows"], 1)
                self.assertEqual(receipt["input_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(source.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
