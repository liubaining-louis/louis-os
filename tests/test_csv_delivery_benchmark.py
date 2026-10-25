from __future__ import annotations

from pathlib import Path
import unittest

from atlas.csv_delivery_benchmark import evaluate_csv_delivery
from atlas.software_micro_missions import csv_automation_demo_files

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks/csv_delivery/cases.json"


class CsvDeliveryBenchmarkTests(unittest.TestCase):
    def test_emitted_standalone_tool_passes_independent_acceptance_cases(self) -> None:
        report = evaluate_csv_delivery(csv_automation_demo_files()["process_csv.py"], CASES)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["case_count"], 12)
        self.assertEqual(report["passed_count"], 12)
        self.assertEqual(report["model_calls"], 0)
        self.assertFalse(report["payment_verified"])

    def test_success_message_without_artifacts_does_not_pass(self) -> None:
        report = evaluate_csv_delivery('print("completed successfully")\n', CASES)
        self.assertFalse(report["passed"])
        self.assertEqual(report["passed_count"], 0)

    def test_modified_source_is_detected_even_when_program_reports_failure(self) -> None:
        script = 'import pathlib, sys\npathlib.Path(sys.argv[1]).write_text("changed")\nprint("invalid_header", file=sys.stderr)\nraise SystemExit(2)\n'
        report = evaluate_csv_delivery(script, CASES)
        self.assertTrue(all("input_modified" in case["errors"] for case in report["cases"]))
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
