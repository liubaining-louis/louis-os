from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.external_signal_ingestion import ExternalSignal, ExternalSignalIngestionGateway


def signal(source: str, external_id: str, **overrides) -> ExternalSignal:
    values = {
        "source": source,
        "external_id": external_id,
        "uri": "https://example.com/source" if source == "web" else "gmail://thread/1",
        "title": "Signal title",
        "content": "Contact buyer@example.com or +33 6 12 34 56 78 for details.",
        "occurred_at": "2026-07-18T12:00:00Z",
        "consent_scope": "commercial_research",
        "read_only": True,
    }
    values.update(overrides)
    return ExternalSignal(**values)


class ExternalSignalIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = ExternalSignalIngestionGateway(maximum_content_chars=200)

    def test_accepts_web_and_gmail_as_different_internal_kinds(self):
        results = self.gateway.ingest([signal("web", "w1"), signal("gmail", "g1")])
        self.assertEqual([item.decision for item in results], ["accepted", "accepted"])
        self.assertEqual([item.kind for item in results], ["evidence", "market_observation"])

    def test_requires_explicit_consent_and_read_only_access(self):
        with self.assertRaises(ValueError):
            self.gateway.ingest([signal("web", "w1", consent_scope="")])
        with self.assertRaises(ValueError):
            self.gateway.ingest([signal("gmail", "g1", read_only=False)])

    def test_redacts_email_and_phone_data(self):
        result = self.gateway.ingest([signal("gmail", "g1")])[0]
        self.assertNotIn("buyer@example.com", result.redacted_content)
        self.assertIn("[REDACTED_EMAIL]", result.redacted_content)
        self.assertIn("[REDACTED_PHONE]", result.redacted_content)

    def test_deduplicates_external_identity(self):
        results = self.gateway.ingest([signal("web", "w1"), signal("web", "w1")])
        self.assertEqual(results[0].decision, "accepted")
        self.assertEqual(results[1].decision, "duplicate")

    def test_rejects_unbounded_content_and_missing_web_uri(self):
        too_long = signal("web", "w1", content="x" * 201)
        missing_uri = signal("web", "w2", uri="")
        results = self.gateway.ingest([too_long, missing_uri])
        self.assertEqual([item.decision for item in results], ["rejected", "rejected"])

    def test_signal_ids_and_hashes_are_deterministic(self):
        first = self.gateway.ingest([signal("web", "w1")])[0]
        second = self.gateway.ingest([signal("web", "w1")])[0]
        self.assertEqual(first.signal_id, second.signal_id)
        self.assertEqual(first.content_hash, second.content_hash)

    def test_writes_auditable_artifact(self):
        items = self.gateway.ingest([signal("web", "w1"), signal("gmail", "g1")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external_signals.json"
            self.gateway.write(items, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["accepted_count"], 2)


if __name__ == "__main__":
    unittest.main()
