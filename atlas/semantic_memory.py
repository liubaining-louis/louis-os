from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_DEFAULT_DIMENSIONS = 256


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.casefold()) if len(token) > 2]


def embed_text(text: str, dimensions: int = _DEFAULT_DIMENSIONS) -> list[float]:
    """Return a deterministic local feature-hash embedding.

    This avoids a network dependency and provides a stable semantic-ish fallback.
    A managed embedding provider can replace it behind the same interface later.
    """
    dimensions = max(int(dimensions), 32)
    counts = Counter(_tokens(text))
    vector = [0.0] * dimensions
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[index] += sign * (1.0 + math.log(float(count)))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def memory_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("content", "")),
            str(item.get("domain", "")),
            " ".join(str(tag) for tag in item.get("tags", [])),
        ]
    ).strip()


def rank_memories_semantically(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    domain: str | None = None,
    limit: int = 5,
    minimum_score: float = 0.05,
) -> list[dict[str, Any]]:
    query_vector = embed_text(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        if item.get("state") != "active":
            continue
        if domain and str(item.get("domain", "")).casefold() != domain.casefold():
            continue
        score = cosine_similarity(query_vector, embed_text(memory_text(item)))
        score += min(max(float(item.get("confidence", 0.0)), 0.0), 1.0) * 0.05
        if score < minimum_score:
            continue
        enriched = dict(item)
        enriched["semantic_score"] = round(score, 6)
        ranked.append((score, enriched))
    ranked.sort(
        key=lambda pair: (pair[0], str(pair[1].get("updated_at", ""))),
        reverse=True,
    )
    bounded_limit = min(max(int(limit), 1), 20)
    return [item for _, item in ranked[:bounded_limit]]
