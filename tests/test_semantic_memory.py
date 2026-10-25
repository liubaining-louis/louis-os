from __future__ import annotations

import unittest
from unittest.mock import patch

from atlas.semantic_memory import cosine_similarity, embed_text, rank_memories_semantically


class SemanticMemoryTests(unittest.TestCase):
    def memory(self, content: str, confidence: float = 1.0) -> dict:
        return {"memory_id": "test", "state": "active", "domain": "misc", "content": content, "confidence": confidence}

    def test_confidence_cannot_admit_an_unrelated_memory(self) -> None:
        self.assertEqual(rank_memories_semantically(
            "normalize csv columns", [self.memory("hotel reservation Edinburgh")]
        ), [])

    def test_hash_collision_is_not_evidence_of_relevance(self) -> None:
        with patch("atlas.semantic_memory.cosine_similarity", return_value=0.9):
            self.assertEqual(rank_memories_semantically(
                "normalize csv columns", [self.memory("hotel reservation Edinburgh")]
            ), [])

    def test_threshold_applies_before_confidence_bonus(self) -> None:
        with patch("atlas.semantic_memory.cosine_similarity", return_value=0.049):
            self.assertEqual(rank_memories_semantically("csv", [self.memory("csv contract")]), [])
        with patch("atlas.semantic_memory.cosine_similarity", return_value=0.051):
            result = rank_memories_semantically("csv", [self.memory("csv contract")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["relevance_score"], 0.051)

    def test_zero_threshold_still_cannot_admit_unrelated_memories(self) -> None:
        self.assertEqual(rank_memories_semantically(
            "csv", [self.memory("hotel booking")], minimum_score=0.0
        ), [])

    def test_empty_or_tokenless_query_abstains(self) -> None:
        for query in ("", "  ", "a to 12", "?!"):
            with self.subTest(query=query):
                self.assertEqual(rank_memories_semantically(query, [self.memory("csv contract")]), [])

    def test_embedding_is_deterministic(self) -> None:
        self.assertEqual(embed_text("Ogatan charcoal customer"), embed_text("Ogatan charcoal customer"))

    def test_related_memory_ranks_first(self) -> None:
        candidates = [
            {
                "memory_id": "1",
                "state": "active",
                "domain": "charcoal",
                "content": "Evert Beumer requested a paid sample box of Ogatan charcoal in the Netherlands.",
                "confidence": 0.9,
                "tags": ["prospect", "sample"],
                "updated_at": "2026-07-17T00:00:00Z",
            },
            {
                "memory_id": "2",
                "state": "active",
                "domain": "travel",
                "content": "The hotel booking in Scotland has free cancellation.",
                "confidence": 0.9,
                "tags": ["hotel"],
                "updated_at": "2026-07-17T00:00:00Z",
            },
        ]
        ranked = rank_memories_semantically(
            "Which charcoal prospect asked for an Ogatan sample?",
            candidates,
            domain="charcoal",
            limit=2,
        )
        self.assertEqual(ranked[0]["memory_id"], "1")
        self.assertGreater(ranked[0]["semantic_score"], 0.05)

    def test_cosine_rejects_mismatched_vectors(self) -> None:
        self.assertEqual(cosine_similarity([1.0], [1.0, 0.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
