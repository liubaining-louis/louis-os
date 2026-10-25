from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_mission_context_benchmark_requires_abstention_and_no_false_positives(self) -> None:
        result = evaluate_retrieval_benchmark(BENCHMARK.with_name("mission_context_v2.json"))
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["case_count"], 12)
        self.assertEqual(result["false_positive_count"], 0)
        self.assertEqual(result["correct_abstentions"], result["abstention_case_count"])
        self.assertEqual(result["exact_pass_count"], 12)

    def test_correct_first_result_does_not_hide_context_contamination(self) -> None:
        payload = {
            "memories": [{"memory_id": "expected"}, {"memory_id": "unrelated"}],
            "cases": [{"case_id": "contaminated", "query": "csv", "expected_memory_ids": ["expected"]}],
            "maximum_false_positives": 0,
            "require_exact_sets": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("atlas.semantic_memory_benchmark.rank_memories_semantically", return_value=payload["memories"]):
                result = evaluate_retrieval_benchmark(path)
        self.assertEqual(result["mean_reciprocal_rank"], 1.0)
        self.assertEqual(result["false_positive_count"], 1)
        self.assertFalse(result["passed"])

    def test_missing_one_of_two_expected_claims_fails_exact_gate(self) -> None:
        payload = {
            "memories": [{"memory_id": "claim-a"}, {"memory_id": "claim-b"}],
            "cases": [{"case_id": "conflict", "query": "effort", "expected_memory_ids": ["claim-a", "claim-b"]}],
            "require_exact_sets": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("atlas.semantic_memory_benchmark.rank_memories_semantically", return_value=payload["memories"][:1]):
                result = evaluate_retrieval_benchmark(path)
        self.assertEqual(result["hit_rate_at_k"], 1.0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["missing_memory_ids"], ["claim-b"])

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
