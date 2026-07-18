from pathlib import Path
import json
import tempfile
import unittest

from atlas.strategic_benchmark import evaluate_strategic_selection_benchmark


FIXTURE = Path("benchmarks/strategic_selection/strategic_selection_v1.json")


class StrategicSelectionBenchmarkTests(unittest.TestCase):
    def test_reference_fixture_passes_all_cases(self) -> None:
        result = evaluate_strategic_selection_benchmark(FIXTURE)

        self.assertTrue(result.passed)
        self.assertEqual(result.version, "strategic_selection_v1")
        self.assertEqual(result.passed_cases, 4)
        self.assertEqual(result.total_cases, 4)
        self.assertEqual(result.failures, ())

    def test_mismatched_expectation_blocks_promotion(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["cases"][0]["expected_action_id"] = "wrong-action"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = evaluate_strategic_selection_benchmark(path)

        self.assertFalse(result.passed)
        self.assertEqual(result.passed_cases, 3)
        self.assertIn("select-highest-safe-value", result.failures[0])

    def test_invalid_empty_dataset_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text('{"version":"strategic_selection_v1","cases":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluate_strategic_selection_benchmark(path)


if __name__ == "__main__":
    unittest.main()
