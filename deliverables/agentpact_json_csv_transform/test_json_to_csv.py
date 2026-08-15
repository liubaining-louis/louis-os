import csv
import json
import tempfile
import unittest
from pathlib import Path

from json_to_csv import TransformError, convert_json_to_csv, normalize_rows


class JsonToCsvTests(unittest.TestCase):
    def test_array_of_objects_with_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            output = root / "output.csv"
            source.write_text(json.dumps([{"name": "Ada", "age": 36}, {"name": "Lin"}]), encoding="utf-8")
            report = convert_json_to_csv(source, output)
            self.assertEqual(report["rows"], 2)
            self.assertEqual(report["columns"], ["age", "name"])
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[1], {"age": "", "name": "Lin"})

    def test_single_object_becomes_one_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            output = root / "output.csv"
            source.write_text('{"b":2,"a":1}', encoding="utf-8")
            report = convert_json_to_csv(source, output)
            self.assertEqual(report["rows"], 1)
            self.assertEqual(report["columns"], ["a", "b"])
            self.assertEqual(output.read_text(encoding="utf-8").splitlines()[0], "a,b")

    def test_nested_values_are_stable_json_cells(self):
        rows, columns = normalize_rows([{"meta": {"z": 2, "a": 1}, "tags": ["x", "y"]}])
        self.assertEqual(columns, ["meta", "tags"])
        self.assertEqual(rows[0]["meta"], '{"a":1,"z":2}')
        self.assertEqual(rows[0]["tags"], '["x","y"]')

    def test_empty_array_produces_valid_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            output = root / "output.csv"
            source.write_text("[]", encoding="utf-8")
            report = convert_json_to_csv(source, output)
            self.assertEqual(report["rows"], 0)
            self.assertEqual(report["columns"], [])
            self.assertEqual(output.read_text(encoding="utf-8"), "")

    def test_non_object_row_is_rejected(self):
        with self.assertRaises(TransformError):
            normalize_rows([{"ok": 1}, "bad"])

    def test_invalid_top_level_scalar_is_rejected(self):
        with self.assertRaises(TransformError):
            normalize_rows(42)

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "broken.json"
            output = root / "output.csv"
            source.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(TransformError, "invalid JSON"):
                convert_json_to_csv(source, output)


if __name__ == "__main__":
    unittest.main()
