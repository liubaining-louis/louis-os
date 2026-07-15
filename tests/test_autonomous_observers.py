import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.autonomous import CycleRecord, FirestoreCycleStore
from atlas.autonomous_observers import (
    collect_observations,
    observe_benchmark_results,
    observe_deployments,
    observe_pull_requests,
    observe_recent_missions,
)


class FakeSnapshot:
    def __init__(self, payload=None):
        self.payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return dict(self.payload)


class FakeDocument:
    def __init__(self, storage, key):
        self.storage = storage
        self.key = key

    def get(self):
        return FakeSnapshot(self.storage.get(self.key))

    def set(self, payload):
        self.storage[self.key] = dict(payload)


class FakeQuery:
    def __init__(self, storage):
        self.storage = storage
        self._limit = 20

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def stream(self):
        values = sorted(self.storage.values(), key=lambda item: item["timestamp"], reverse=True)
        return [FakeSnapshot(value) for value in values[: self._limit]]


class FakeCollection(FakeQuery):
    def document(self, key):
        return FakeDocument(self.storage, key)


class FakeClient:
    def __init__(self):
        self.storage = {}

    def collection(self, _name):
        return FakeCollection(self.storage)


class AutonomousObserverTests(unittest.TestCase):
    def test_firestore_cycle_store_is_idempotent_and_listable(self):
        client = FakeClient()
        store = FirestoreCycleStore(client=client, collection_name="cycles")
        first = CycleRecord("c1", "2026-01-01T00:00:00+00:00", "simulated", True, None, None, ["observe"])
        changed = CycleRecord("c1", "2026-01-02T00:00:00+00:00", "completed", False, None, None, ["observe"])
        second = CycleRecord("c2", "2026-01-03T00:00:00+00:00", "simulated", True, None, None, ["observe"])

        store.save(first)
        store.save(changed)
        store.save(second)

        self.assertEqual(store.get("c1").status, "simulated")
        self.assertEqual([item.cycle_id for item in store.list(limit=2)], ["c2", "c1"])

    def test_failed_and_slow_missions_become_opportunities(self):
        missions = [
            {"mission_id": "m1", "status": "failed", "latency_ms": 15000, "revision_count": 0},
            {"mission_id": "m2", "status": "completed", "latency_ms": 100, "revision_count": 2},
        ]
        with patch("atlas.autonomous_observers.list_missions", return_value=missions):
            opportunities = observe_recent_missions()
        ids = {item.id for item in opportunities}
        self.assertIn("mission-failure-m1", ids)
        self.assertIn("mission-latency-m1", ids)
        self.assertIn("mission-quality-m2", ids)

    def test_benchmark_regression_is_detected(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "summary.json"
            path.write_text(json.dumps({"total": 10, "failed": 2, "pass_rate": 0.8}), encoding="utf-8")
            opportunities = observe_benchmark_results(path)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].id, "benchmark-regression")

    def test_pr_and_deployment_failures_are_observed(self):
        pr_opportunities = observe_pull_requests([
            {"number": 17, "state": "open", "draft": True, "ci_status": "failure"}
        ])
        deployment_opportunities = observe_deployments([
            {"id": "run-1", "status": "failed"}
        ])
        self.assertEqual(pr_opportunities[0].id, "pr-ci-17")
        self.assertEqual(deployment_opportunities[0].id, "deployment-run-1")

    def test_collect_observations_is_deterministically_sorted(self):
        with patch("atlas.autonomous_observers.list_missions", return_value=[]):
            opportunities = collect_observations(
                pull_requests=[{"number": 2, "state": "open", "draft": True}],
                deployments=[{"id": "1", "status": "failed"}],
                summary_path=Path("missing-summary.json"),
            )
        self.assertEqual([item.id for item in opportunities], sorted(item.id for item in opportunities))


if __name__ == "__main__":
    unittest.main()
