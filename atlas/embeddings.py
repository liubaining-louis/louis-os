from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Minimal provider contract for semantic memory backends."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Deterministic, dependency-free embeddings for dry-run and tests.

    Tokens are projected into a fixed-size signed feature space. This is not a
    production language model, but it validates the provider/index contract
    without external APIs, secrets or network access.
    """

    def __init__(self, dimensions: int = 128):
        if dimensions < 16:
            raise ValueError("dimensions must be at least 16")
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\w-]+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return vector if norm == 0 else [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    return sum(a * b for a, b in zip(left, right))


def semantic_rank(
    query: str,
    records: Sequence[dict],
    provider: EmbeddingProvider,
    *,
    text_key: str = "content",
) -> list[tuple[float, dict]]:
    """Rank records by semantic similarity, preserving deterministic ties."""

    if not records:
        return []
    texts = [query, *[str(record.get(text_key, "")) for record in records]]
    vectors = provider.embed(texts)
    query_vector = vectors[0]
    ranked = [
        (cosine_similarity(query_vector, vector), record)
        for vector, record in zip(vectors[1:], records)
    ]
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("memory_id", ""))))
    return ranked
