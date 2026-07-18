from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from atlas.opportunity_discovery import AutonomousOpportunityDiscovery
from atlas.real_world_sources import (
    CompositeOpportunitySource,
    HttpJsonOpportunitySource,
    HttpSourcePolicy,
)


def _payload(**overrides: object) -> bytes:
    item = {
        "source_id": "market-1",
        "source_url": "https://evidence.example/opportunities/1",
        "title": "Automated supplier qualification",
        "problem": "Industrial buyers spend too much time qualifying suppliers.",
        "target_customer": "European industrial SMEs",
        "proposed_offer": "Evidence-backed supplier qualification report",
        "expected_value": 0.9,
        "autonomy": 0.92,
        "learning_value": 0.8,
        "speed": 0.75,
        "human_dependency": 0.15,
        "cost": 0.2,
        "risk": 0.25,
    }
    item.update(overrides)
    return json.dumps({"items": [item]}).encode("utf-8")


def _source(payload: bytes | None = None) -> HttpJsonOpportunitySource:
    def fetcher(request: Request, timeout: float) -> bytes:
        if request.full_url != "https://feed.example/opportunities.json":
            raise AssertionError("unexpected endpoint")
        if request.get_header("Accept") != "application/json":
            raise AssertionError("missing JSON accept header")
        if timeout != 3.0:
            raise AssertionError("unexpected timeout")
        return payload if payload is not None else _payload()

    return HttpJsonOpportunitySource(
        source_name="market-feed",
        endpoint_url="https://feed.example/opportunities.json",
        policy=HttpSourcePolicy(
            allowed_hosts=("feed.example",),
            timeout_seconds=3.0,
            maximum_bytes=20_000,
        ),
        fetcher=fetcher,
    )


class RealWorldSourceTests(unittest.TestCase):
    def test_collects_real_world_json_signal(self):
        signals = list(_source().collect())
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].source_id, "market-1")
        self.assertEqual(signals[0].autonomy, 0.92)
        signals[0].validate()

    def test_rejects_non_allowlisted_or_insecure_endpoint(self):
        policy = HttpSourcePolicy(allowed_hosts=("feed.example",))
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            HttpJsonOpportunitySource(
                source_name="bad",
                endpoint_url="http://feed.example/items",
                policy=policy,
            )
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            HttpJsonOpportunitySource(
                source_name="bad",
                endpoint_url="https://other.example/items",
                policy=policy,
            )

    def test_enforces_response_size_and_json_schema(self):
        source = HttpJsonOpportunitySource(
            source_name="large",
            endpoint_url="https://feed.example/items",
            policy=HttpSourcePolicy(allowed_hosts=("feed.example",), maximum_bytes=4),
            fetcher=lambda request, timeout: b"12345",
        )
        with self.assertRaisesRegex(ValueError, "maximum_bytes"):
            list(source.collect())
        with self.assertRaisesRegex(ValueError, "items list"):
            list(_source(json.dumps({"wrong": []}).encode()).collect())

    def test_rejects_missing_numeric_score(self):
        with self.assertRaisesRegex(ValueError, "expected_value"):
            list(_source(_payload(expected_value="high")).collect())

    def test_external_source_flows_into_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "discovery.json"
            result = AutonomousOpportunityDiscovery().discover(
                sources=[_source()],
                output_path=output,
            )
            self.assertEqual(result.signal_count, 1)
            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(result.opportunities[0].title, "Automated supplier qualification")
            self.assertTrue(output.exists())

    def test_composite_source_is_deterministic(self):
        first = _source(_payload(source_id="first"))
        second = _source(_payload(source_id="second", title="Second opportunity"))
        combined = CompositeOpportunitySource("combined", [first, second])
        self.assertEqual(
            [signal.source_id for signal in combined.collect()],
            ["first", "second"],
        )


if __name__ == "__main__":
    unittest.main()
