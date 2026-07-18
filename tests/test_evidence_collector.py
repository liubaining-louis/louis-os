from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.evidence_collector import BoundedEvidenceCollector, CollectionRequest, SourceRecord


class FakeAdapter:
    def __init__(self, records=None, error: Exception | None = None):
        self.records = records or []
        self.error = error

    def collect(self, request):
        if self.error:
            raise self.error
        return self.records


def source(source_id: str, uri: str, **overrides):
    values = {
        "source_id": source_id,
        "uri": uri,
        "title": source_id,
        "claim": f"claim-{source_id}",
        "source_kind": "official",
        "reliability": 0.9,
        "freshness": 0.9,
        "retrieved_at": "2026-07-18T00:00:00Z",
    }
    values.update(overrides)
    return SourceRecord(**values)


class EvidenceCollectorTests(unittest.TestCase):
    def test_accepts_high_quality_provenanced_source(self):
        request = CollectionRequest("task-1", "market demand", "demand", 2)
        results = BoundedEvidenceCollector().execute(
            [request], {"demand": FakeAdapter([source("s1", "https://official.example/a")])}
        )
        self.assertEqual(results[0].decision, "accepted")

    def test_rejects_unknown_low_quality_and_stale_sources(self):
        request = CollectionRequest("task-1", "market demand", "demand", 5)
        records = [
            source("unknown", "https://x.example/1", source_kind="unknown"),
            source("weak", "https://x.example/2", reliability=0.2),
            source("stale", "https://x.example/3", freshness=0.1),
        ]
        results = BoundedEvidenceCollector().execute([request], {"demand": FakeAdapter(records)})
        self.assertEqual([item.decision for item in results], ["rejected", "rejected", "rejected"])

    def test_deduplicates_source_uris_across_tasks(self):
        requests = [
            CollectionRequest("t1", "q1", "demand", 1),
            CollectionRequest("t2", "q2", "pricing", 1),
        ]
        shared = source("s", "https://official.example/shared")
        results = BoundedEvidenceCollector().execute(
            requests,
            {"demand": FakeAdapter([shared]), "pricing": FakeAdapter([shared])},
        )
        self.assertEqual(results[0].decision, "accepted")
        self.assertEqual(results[1].decision, "rejected")
        self.assertIn("duplicate", results[1].reason)

    def test_enforces_global_and_per_task_quotas(self):
        request = CollectionRequest("t1", "q", "demand", 3)
        records = [source(f"s{i}", f"https://official.example/{i}") for i in range(4)]
        results = BoundedEvidenceCollector(maximum_total_sources=2).execute(
            [request], {"demand": FakeAdapter(records)}
        )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[-1].decision, "quota_exceeded")

    def test_isolates_missing_or_failing_adapter(self):
        missing = BoundedEvidenceCollector().execute(
            [CollectionRequest("t1", "q", "risk", 1)], {}
        )
        failing = BoundedEvidenceCollector().execute(
            [CollectionRequest("t2", "q", "risk", 1)], {"risk": FakeAdapter(error=RuntimeError("boom"))}
        )
        self.assertEqual(missing[0].decision, "adapter_error")
        self.assertEqual(failing[0].decision, "adapter_error")

    def test_writes_auditable_artifact(self):
        request = CollectionRequest("task-1", "market demand", "demand", 1)
        collector = BoundedEvidenceCollector()
        results = collector.execute(
            [request], {"demand": FakeAdapter([source("s1", "https://official.example/a")])}
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            collector.write(results, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["accepted_count"], 1)


if __name__ == "__main__":
    unittest.main()
