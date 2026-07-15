from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.memory import create_memory, format_memory_context, get_memory, retrieve_memories


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"MEMORY_STORE": "local"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.root_patch = patch("atlas.memory.ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_create_and_get_memory(self) -> None:
        record = create_memory(
            memory_type="decision",
            domain="business",
            content="Prioritize technical B2B products with reusable assets.",
            confidence=0.9,
            tags=["B2B", "strategy"],
            source="conversation",
        )
        stored = get_memory(record.memory_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["memory_type"], "decision")
        self.assertEqual(stored["tags"], ["b2b", "strategy"])

    def test_rejects_secret_like_content(self) -> None:
        with self.assertRaises(ValueError):
            create_memory(
                memory_type="fact",
                domain="infra",
                content="API_KEY=gsk_example_secret_value",
                confidence=1.0,
            )

    def test_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValueError):
            create_memory("fact", "industry", "A fact", 1.2)

    def test_retrieves_relevant_domain_memory(self) -> None:
        create_memory("fact", "industry", "DLC reduces friction and wear.", 0.8, ["coating"])
        create_memory("fact", "travel", "Edinburgh booking dates are in September.", 0.9)
        results = retrieve_memories("compare DLC coating wear", domain="industry")
        self.assertEqual(len(results), 1)
        self.assertIn("DLC", results[0]["content"])

    def test_formats_bounded_prompt_context(self) -> None:
        memories = [
            {
                "memory_type": "procedure",
                "domain": "industry",
                "confidence": 0.91,
                "content": "Verify coating thickness before comparing wear results.",
            },
            {
                "memory_type": "fact",
                "domain": "industry",
                "confidence": 0.8,
                "content": "This second memory must be excluded by the character budget.",
            },
        ]
        context = format_memory_context(memories, max_chars=110)
        self.assertIn("procedure/industry", context)
        self.assertIn("Verify coating thickness", context)
        self.assertNotIn("second memory", context)


if __name__ == "__main__":
    unittest.main()
