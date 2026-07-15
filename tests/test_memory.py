from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atlas.memory import LocalMemoryStore, build_memory


class MemoryTests(unittest.TestCase):
    def test_builds_typed_memory_with_normalized_tags(self) -> None:
        record = build_memory(
            "Fact",
            {"subject": "Ogatan", "statement": "High-density charcoal"},
            {"source": "user", "conversation_id": "charcoal-project"},
            0.9,
            tags=["Business", "charcoal", "business"],
        )
        self.assertEqual(record.memory_type, "fact")
        self.assertEqual(record.tags, ["business", "charcoal"])
        self.assertEqual(record.lifecycle_state, "active")

    def test_rejects_unknown_memory_type(self) -> None:
        with self.assertRaises(ValueError):
            build_memory("note", {"text": "x"}, {"source": "test"}, 0.5)

    def test_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValueError):
            build_memory("fact", {"text": "x"}, {"source": "test"}, 1.1)

    def test_rejects_secret_like_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret-like field"):
            build_memory(
                "preference",
                {"api_key": "not-even-a-real-key"},
                {"source": "test"},
                0.8,
            )

    def test_rejects_secret_like_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret-like value"):
            build_memory(
                "fact",
                {"text": "credential sk-1234567890abcdefghijkl"},
                {"source": "test"},
                0.8,
            )

    def test_local_store_filters_archived_and_ranks_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalMemoryStore(Path(temp_dir))
            relevant = build_memory(
                "decision",
                {"project": "charcoal", "decision": "target European wholesalers"},
                {"source": "conversation"},
                0.95,
                tags=["business", "charcoal"],
                memory_id="relevant",
            )
            weak = build_memory(
                "fact",
                {"project": "charcoal", "statement": "sample received"},
                {"source": "conversation"},
                0.4,
                tags=["business", "charcoal"],
                memory_id="weak",
            )
            archived = build_memory(
                "outcome",
                {"project": "charcoal", "outcome": "obsolete quote"},
                {"source": "conversation"},
                1.0,
                tags=["business", "charcoal"],
                lifecycle_state="archived",
                memory_id="archived",
            )
            for record in (weak, archived, relevant):
                store.save(record)

            results = store.search("charcoal wholesalers", tags=["business"], limit=10)
            self.assertEqual([item["memory_id"] for item in results], ["relevant", "weak"])
            self.assertIsNone(store.get("missing"))
            self.assertEqual(store.get("relevant")["memory_type"], "decision")


if __name__ == "__main__":
    unittest.main()
