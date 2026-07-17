from __future__ import annotations

import unittest

from atlas.semantic_memory import cosine_similarity, embed_text, rank_memories_semantically


class SemanticMemoryTests(unittest.TestCase):
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
