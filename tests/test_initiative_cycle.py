import tempfile
import unittest
from pathlib import Path

from atlas.initiative import ActionBudget, Opportunity
from atlas.initiative_cycle import (
    CycleObservation,
    CycleRecord,
    FirestoreCycleStore,
    JsonlCycleStore,
    run_dry_cycle,
)


class FakeSnapshot:
    def __init__(self, payload):
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return self._payload


class FakeDocument:
    def __init__(self, storage, key):
        self.storage = storage
        self.key = key

    def get(self):
        return FakeSnapshot(self.storage.get(self.key))

    def create(self, payload):
        if self.key in self.storage:
            raise RuntimeError("already exists")
        self.storage[self.key] = dict(payload)


class FakeCollection:
    def __init__(self):
        self.storage = {}

    def document(self, key):
        return FakeDocument(self.storage, key)


class InitiativeCycleTests(unittest.TestCase):
    def _store(self, directory: str) -> JsonlCycleStore:
        return JsonlCycleStore(Path(directory) / "cycles.jsonl")

    def test_full_cycle_is_recorded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = {"planner": 0, "simulator": 0}

            def planner(opportunity, observations):
                calls["planner"] += 1
                return f"simulate {opportunity.key} from {len(observations)} observations"

            def simulator(opportunity, plan):
                calls["simulator"] += 1
                return {"passed": True, "regression": False, "evidence": "3 targeted tests passed"}

            kwargs = dict(
                observations=[CycleObservation("ci", "run-1", "main is green")],
                opportunities=[Opportunity("initiative-cycle", 10, 9, 0.9, 3, risk=1)],
                budget=ActionBudget(),
                store=self._store(directory),
                planner=planner,
                simulator=simulator,
            )
            first = run_dry_cycle(**kwargs)
            second = run_dry_cycle(**kwargs)

            self.assertEqual(first, second)
            self.assertEqual(first.status, "validated")
            self.assertEqual(
                first.stages,
                ("observe", "prioritize", "plan", "simulate", "evaluate", "learn"),
            )
            self.assertEqual(calls, {"planner": 1, "simulator": 1})

    def test_firestore_store_round_trip_and_duplicate_create(self):
        collection = FakeCollection()
        store = FirestoreCycleStore(collection)
        record = CycleRecord(
            cycle_id="cycle-1",
            status="validated",
            stages=("observe", "learn"),
            selected_opportunity="x",
            plan="plan",
            simulated_result="evidence",
            evaluation="passed",
            learned="retain",
        )

        first = store.append_once(record)
        second = store.append_once(record)

        self.assertEqual(first, record)
        self.assertEqual(second, record)
        self.assertEqual(store.get("cycle-1"), record)
        self.assertEqual(len(collection.storage), 1)

    def test_firestore_store_propagates_non_duplicate_failure(self):
        class FailingDocument(FakeDocument):
            def create(self, payload):
                raise RuntimeError("service unavailable")

        class FailingCollection(FakeCollection):
            def document(self, key):
                return FailingDocument(self.storage, key)

        store = FirestoreCycleStore(FailingCollection())
        record = CycleRecord("cycle-2", "rejected", ("observe",), None, None, None, "failed", "retry changed")

        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            store.append_once(record)

    def test_regression_refuses_promotion_and_records_rejected_hypothesis(self):
        with tempfile.TemporaryDirectory() as directory:
            record = run_dry_cycle(
                observations=[CycleObservation("benchmark", "semantic-v1", "MRR decreased")],
                opportunities=[Opportunity("ranking-change", 8, 8, 0.8, 2, risk=1)],
                budget=ActionBudget(),
                store=self._store(directory),
                planner=lambda *_: "simulate ranking change",
                simulator=lambda *_: {
                    "passed": True,
                    "regression": True,
                    "evidence": "MRR 0.80 -> 0.72",
                },
            )
            self.assertEqual(record.status, "rejected")
            self.assertIn("Promotion refused", record.evaluation)
            self.assertIn("do not repeat", record.learned)

    def test_unsafe_only_cycle_becomes_approval_required_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            record = run_dry_cycle(
                observations=[CycleObservation("repo", "main", "IAM proposal detected")],
                opportunities=[Opportunity("change-iam", 10, 10, 1.0, 1, risk=1, requires_approval=True)],
                budget=ActionBudget(),
                store=self._store(directory),
                planner=lambda *_: self.fail("planner must not run"),
                simulator=lambda *_: self.fail("simulator must not run"),
            )
            self.assertEqual(record.status, "approval_required")
            self.assertTrue(record.approval_required)
            self.assertEqual(record.stages, ("observe", "prioritize", "evaluate", "learn"))

    def test_missing_simulation_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_dry_cycle(
                    observations=[],
                    opportunities=[Opportunity("x", 5, 5, 1.0, 1)],
                    budget=ActionBudget(),
                    store=self._store(directory),
                    planner=lambda *_: "simulate",
                    simulator=lambda *_: {"passed": True, "regression": False},
                )


if __name__ == "__main__":
    unittest.main()
