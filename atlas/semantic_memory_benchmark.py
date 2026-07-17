from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .semantic_memory import rank_memories_semantically


def evaluate_retrieval_benchmark(path: str | Path, *, limit: int = 3) -> dict[str, Any]:
    """Evaluate semantic retrieval with hit-rate@k and mean reciprocal rank.

    The benchmark is deterministic and contains no provider or network dependency.
    Promotion passes only when both configured thresholds are met.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    memories = list(payload.get("memories", []))
    cases = list(payload.get("cases", []))
    if not memories or not cases:
        raise ValueError("semantic retrieval benchmark requires memories and cases")

    hits = 0
    reciprocal_rank_total = 0.0
    results: list[dict[str, Any]] = []
    bounded_limit = min(max(int(limit), 1), 20)

    for case in cases:
        expected_id = str(case["expected_memory_id"])
        ranked = rank_memories_semantically(
            str(case["query"]),
            memories,
            domain=case.get("domain"),
            limit=bounded_limit,
            minimum_score=0.0,
        )
        ranked_ids = [str(item.get("memory_id", "")) for item in ranked]
        rank = ranked_ids.index(expected_id) + 1 if expected_id in ranked_ids else None
        if rank is not None:
            hits += 1
            reciprocal_rank_total += 1.0 / rank
        results.append(
            {
                "case_id": str(case["case_id"]),
                "expected_memory_id": expected_id,
                "rank": rank,
                "retrieved_memory_ids": ranked_ids,
            }
        )

    case_count = len(cases)
    hit_rate_at_k = hits / case_count
    mean_reciprocal_rank = reciprocal_rank_total / case_count
    minimum_hit_rate = float(payload.get("minimum_hit_rate_at_3", 1.0))
    minimum_mrr = float(payload.get("minimum_mrr", 1.0))

    return {
        "benchmark_id": str(payload.get("benchmark_id", Path(path).stem)),
        "case_count": case_count,
        "limit": bounded_limit,
        "hit_rate_at_k": round(hit_rate_at_k, 6),
        "mean_reciprocal_rank": round(mean_reciprocal_rank, 6),
        "minimum_hit_rate_at_3": minimum_hit_rate,
        "minimum_mrr": minimum_mrr,
        "passed": hit_rate_at_k >= minimum_hit_rate and mean_reciprocal_rank >= minimum_mrr,
        "results": results,
    }
