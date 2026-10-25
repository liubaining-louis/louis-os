from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .semantic_memory import rank_memories_semantically


def evaluate_retrieval_benchmark(path: str | Path, *, limit: int = 3) -> dict[str, Any]:
    """Evaluate production retrieval thresholds, abstention and contamination.

    The benchmark is deterministic and contains no provider or network dependency.
    v1 hit-rate/MRR gates remain; v2 can additionally require exact result sets.
    These are memory-context checks, not evidence of paid mission completion.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    memories = list(payload.get("memories", []))
    cases = list(payload.get("cases", []))
    if not memories or not cases:
        raise ValueError("semantic retrieval benchmark requires memories and cases")

    hits = 0
    positive_cases = 0
    abstention_cases = 0
    correct_abstentions = 0
    exact_passes = 0
    false_positives = 0
    reciprocal_rank_total = 0.0
    results: list[dict[str, Any]] = []
    bounded_limit = min(max(int(limit), 1), 20)

    for case in cases:
        expected_ids = (
            [str(value) for value in case["expected_memory_ids"]]
            if "expected_memory_ids" in case
            else [str(case["expected_memory_id"])]
        )
        expected = set(expected_ids)
        ranked = rank_memories_semantically(
            str(case["query"]),
            memories,
            domain=case.get("domain"),
            limit=bounded_limit,
        )
        ranked_ids = [str(item.get("memory_id", "")) for item in ranked]
        rank = next((index for index, value in enumerate(ranked_ids, 1) if value in expected), None)
        unexpected = sorted(set(ranked_ids) - expected)
        missing = sorted(expected - set(ranked_ids))
        false_positives += len(unexpected)
        exact_pass = not unexpected and not missing
        exact_passes += int(exact_pass)
        if expected:
            positive_cases += 1
        else:
            abstention_cases += 1
            correct_abstentions += int(not ranked_ids)
        if rank is not None:
            hits += 1
            reciprocal_rank_total += 1.0 / rank
        results.append(
            {
                "case_id": str(case["case_id"]),
                "expected_memory_id": expected_ids[0] if expected_ids else None,
                "expected_memory_ids": expected_ids,
                "rank": rank,
                "retrieved_memory_ids": ranked_ids,
                "unexpected_memory_ids": unexpected,
                "missing_memory_ids": missing,
                "exact_pass": exact_pass,
            }
        )

    case_count = len(cases)
    hit_rate_at_k = hits / positive_cases if positive_cases else 1.0
    mean_reciprocal_rank = reciprocal_rank_total / positive_cases if positive_cases else 1.0
    minimum_hit_rate = float(payload.get("minimum_hit_rate_at_3", 1.0))
    minimum_mrr = float(payload.get("minimum_mrr", 1.0))
    maximum_false_positives = payload.get("maximum_false_positives")
    require_exact_sets = payload.get("require_exact_sets") is True
    quality_passed = (
        hit_rate_at_k >= minimum_hit_rate
        and mean_reciprocal_rank >= minimum_mrr
        and (maximum_false_positives is None or false_positives <= int(maximum_false_positives))
        and (not require_exact_sets or exact_passes == case_count)
        and correct_abstentions == abstention_cases
    )

    return {
        "benchmark_id": str(payload.get("benchmark_id", Path(path).stem)),
        "case_count": case_count,
        "positive_case_count": positive_cases,
        "abstention_case_count": abstention_cases,
        "correct_abstentions": correct_abstentions,
        "false_positive_count": false_positives,
        "exact_pass_count": exact_passes,
        "limit": bounded_limit,
        "hit_rate_at_k": round(hit_rate_at_k, 6),
        "mean_reciprocal_rank": round(mean_reciprocal_rank, 6),
        "minimum_hit_rate_at_3": minimum_hit_rate,
        "minimum_mrr": minimum_mrr,
        "passed": quality_passed,
        "results": results,
    }
