from __future__ import annotations

import unittest

from atlas.embeddings import HashEmbeddingProvider, cosine_similarity, semantic_rank


class EmbeddingTests(unittest.TestCase):
    def test_embeddings_are_deterministic_and_normalized(self) -> None:
        provider = HashEmbeddingProvider(dimensions=64)
        first, second = provider.embed(["DLC coating wear", "DLC coating wear"])
        self.assertEqual(first, second)
        self.assertAlmostEqual(cosine_similarity(first, first), 1.0, places=6)

    def test_semantic_rank_prioritizes_shared_concepts(self) -> None:
        provider = HashEmbeddingProvider(dimensions=128)
        records = [
            {"memory_id": "travel", "content": "Edinburgh hotel booking in September"},
            {"memory_id": "coating", "content": "DLC coating reduces friction and wear"},
        ]
        ranked = semantic_rank("compare DLC wear coating", records, provider)
        self.assertEqual(ranked[0][1]["memory_id"], "coating")
        self.assertGreater(ranked[0][0], ranked[1][0])

    def test_invalid_dimensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HashEmbeddingProvider(dimensions=8)

    def test_vector_dimension_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cosine_similarity([1.0], [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
