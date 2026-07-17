from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.semantic_memory_benchmark import evaluate_retrieval_benchmark


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "semantic_memory" / "retrieval_v1.json"


class SemanticMemoryBenchmarkTests(unittest.TestCase):
    def test_reference_benchmark_passes_quality_gates(self) -> None:
        result = evaluate_retrieval_benchmark(BENCHMARK)
        self.assertTrue(result["passed"])
        self.assertEqual(result["case_count"], 3)
        self.assertGreaterEqual(result["hit_rate_at_k"], 1.0)
        self.assertGreaterEqual(result["mean_reciprocal_rank"], 0.8)
        self.assertTrue(all(case["rank"] is not None for case in result["results"]))

    def test_empty_benchmark_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text(json.dumps({"memories": [], "cases": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluate_retrieval_benchmark(path)

    def test_failed_threshold_blocks_promotion(self) -> None:
        payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        payload["minimum_mrr"] = 1.1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = evaluate_retrieval_benchmark(path)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
