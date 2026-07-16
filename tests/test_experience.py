from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from atlas.experience import record_mission_experience


class ExperienceTests(unittest.TestCase):
    def test_completed_mission_creates_outcome_memory(self) -> None:
        memory = SimpleNamespace(memory_id="mem-1")
        with patch("atlas.experience.create_memory", return_value=memory) as create_memory:
            memory_id = record_mission_experience(
                mission_id="mission-1",
                mission_type="research",
                objective="Compare three suppliers",
                status="completed",
                workflow="research-analysis",
                risk_level="low",
                revision_count=1,
                provider="groq",
                model="model-a",
                latency_ms=1200,
                context={"domain": "business"},
            )

        self.assertEqual(memory_id, "mem-1")
        kwargs = create_memory.call_args.kwargs
        self.assertEqual(kwargs["memory_type"], "outcome")
        self.assertEqual(kwargs["domain"], "business")
        self.assertEqual(kwargs["source"], "louis-os:auto-evaluation")
        payload = json.loads(kwargs["content"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["revision_count"], 1)

    def test_unknown_status_is_not_memorized(self) -> None:
        with patch("atlas.experience.create_memory") as create_memory:
            result = record_mission_experience(
                mission_id="mission-2",
                mission_type="general",
                objective="Test",
                status="running",
                workflow="general",
                risk_level="low",
                revision_count=0,
                provider="none",
                model="none",
                latency_ms=10,
                context={},
            )
        self.assertIsNone(result)
        create_memory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
