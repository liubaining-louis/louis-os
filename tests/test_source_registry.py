from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.source_registry import OpportunitySourceRegistry, SourceRegistryEntry


class OpportunitySourceRegistryTests(unittest.TestCase):
    def test_loads_enabled_sources_from_versioned_config(self) -> None:
        payload = {
            "schema_version": "1.0",
            "sources": [
                {
                    "name": "primary",
                    "endpoint_url": "https://feed.example/opportunities.json",
                    "allowed_hosts": ["feed.example"],
                    "timeout_seconds": 3,
                    "maximum_bytes": 20000,
                    "enabled": True,
                },
                {
                    "name": "disabled",
                    "endpoint_url": "https://other.example/items.json",
                    "allowed_hosts": ["other.example"],
                    "enabled": False,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            registry = OpportunitySourceRegistry.from_file(path)

        self.assertEqual(len(registry.entries), 2)
        sources = registry.build_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_name, "primary")

    def test_rejects_duplicate_names(self) -> None:
        entry = SourceRegistryEntry(
            name="duplicate",
            endpoint_url="https://feed.example/items",
            allowed_hosts=("feed.example",),
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            OpportunitySourceRegistry([entry, entry])

    def test_rejects_host_outside_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            OpportunitySourceRegistry([
                SourceRegistryEntry(
                    name="bad",
                    endpoint_url="https://other.example/items",
                    allowed_hosts=("feed.example",),
                )
            ])

    def test_rejects_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sources.json"
            path.write_text(json.dumps({"schema_version": "2.0", "sources": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                OpportunitySourceRegistry.from_file(path)


if __name__ == "__main__":
    unittest.main()
