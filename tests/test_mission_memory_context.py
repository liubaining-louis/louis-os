"""Offline context pipeline checks; model responses are fixtures, not quality evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from atlas.memory import retrieve_memories
from atlas.missions import run_mission
from atlas.providers import ModelResponse

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/semantic_memory/mission_context_v2.json"


class MissionMemoryContextTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        directory = self.root / "results/memories"
        directory.mkdir(parents=True)
        for memory in self.fixture["memories"]:
            (directory / (memory["memory_id"] + ".json")).write_text(
                json.dumps(memory), encoding="utf-8"
            )
        for target in ("atlas.memory.ROOT", "atlas.storage.ROOT"):
            manager = patch(target, self.root)
            manager.start()
            self.addCleanup(manager.stop)
        environment = patch.dict(os.environ, {"MEMORY_STORE": "local", "MISSION_STORE": "local"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_all_cases_through_persisted_semantic_hybrid_and_lexical_paths(self) -> None:
        for mode in ("semantic", "hybrid", "lexical"):
            with patch.dict(os.environ, {"MEMORY_RETRIEVAL_MODE": mode}):
                for case in self.fixture["cases"]:
                    with self.subTest(mode=mode, case=case["case_id"]):
                        retrieved = retrieve_memories(case["query"], domain=case.get("domain"), limit=3)
                        self.assertEqual(
                            {item["memory_id"] for item in retrieved},
                            set(case["expected_memory_ids"]),
                        )

    def test_hybrid_lexical_fallback_cannot_restore_unrelated_memories(self) -> None:
        with patch.dict(os.environ, {"MEMORY_RETRIEVAL_MODE": "hybrid"}), \
             patch("atlas.memory.rank_memories_semantically", return_value=[]):
            self.assertEqual(retrieve_memories("quasar luminosity"), [])
            self.assertEqual(retrieve_memories("a to 12"), [])
            self.assertEqual(
                [item["memory_id"] for item in retrieve_memories("api")],
                ["api-timeout"],
            )

    def run_fixture_mission(self, query: str, domain: str):
        with patch("atlas.orchestrator.complete", side_effect=[
            ModelResponse("fixture", "no-network", "Offline fixture answer."),
            ModelResponse("fixture", "no-network", "VERDICT: PASS\nFixture only."),
        ]) as model, patch("atlas.missions.record_mission_experience", return_value=None):
            record = run_mission("research", query, {"domain": domain})
        self.assertEqual(model.call_count, 2)
        stored = json.loads((self.root / "results/missions" / (record.mission_id + ".json")).read_text())
        self.assertEqual(stored["memories_used"], record.memories_used)
        return record, model.call_args_list[0].args[0]

    def test_three_task_contexts_reach_specialist_without_unrelated_memories(self) -> None:
        cases = [
            ("Normalize CSV columns", "data", "csv-contract"),
            ("Explain webhook API timeout", "code", "api-timeout"),
            ("Explain comparison sources dates", "research", "research-evidence"),
        ]
        for query, domain, expected in cases:
            with self.subTest(domain=domain):
                record, prompt = self.run_fixture_mission(query, domain)
                self.assertEqual(record.memories_used, [expected])
                self.assertNotIn("hotel reservation", prompt)
                self.assertIn("context, not verified truth", prompt)

    def test_abstention_reaches_mission_without_an_invented_memory_context(self) -> None:
        record, prompt = self.run_fixture_mission("Explain quasar luminosity", "travel")
        self.assertEqual(record.memories_used, [])
        self.assertNotIn("Potentially relevant durable memory", prompt)
        self.assertNotIn("hotel reservation", prompt)

    def test_contradictory_claims_stay_visible_not_resolved_by_confidence(self) -> None:
        record, prompt = self.run_fixture_mission("Explain autonomous mission effort ceiling", "policy")
        self.assertEqual(set(record.memories_used), {"effort-three", "effort-eight"})
        self.assertIn("three hours", prompt)
        self.assertIn("eight hours", prompt)
        self.assertIn("context, not verified truth", prompt)


if __name__ == "__main__":
    unittest.main()
