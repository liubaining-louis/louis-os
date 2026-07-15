import unittest
from unittest.mock import patch

from atlas.autonomous import CycleRecord, Opportunity
from atlas.autonomous_service import (
    get_autonomous_cycle,
    list_autonomous_cycles,
    run_autonomous_cycle,
)


class FakeStore:
    def __init__(self):
        self.records = {}

    def get(self, cycle_id):
        return self.records.get(cycle_id)

    def save(self, record):
        self.records.setdefault(record.cycle_id, record)

    def list(self, limit=20):
        return list(self.records.values())[:limit]


class AutonomousServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.opportunity = Opportunity(
            "mission-failure-1",
            "Diagnose failed mission 1",
            0.9,
            0.95,
            0.95,
            0.35,
            0.1,
        )

    def test_run_cycle_collects_observations_and_persists_dry_run(self):
        with patch("atlas.autonomous_service.get_cycle_store", return_value=self.store), patch(
            "atlas.autonomous_service.collect_observations", return_value=[self.opportunity]
        ):
            record = run_autonomous_cycle(observation_key="service-test")

        self.assertEqual(record.status, "simulated")
        self.assertTrue(record.dry_run)
        self.assertEqual(record.selected_opportunity["id"], "mission-failure-1")
        self.assertIsNotNone(self.store.get(record.cycle_id))

    def test_list_and_get_return_serializable_payloads(self):
        record = CycleRecord(
            cycle_id="cycle-1",
            timestamp="2026-01-01T00:00:00+00:00",
            status="simulated",
            dry_run=True,
            selected_opportunity=None,
            score=None,
            stages=["observe", "learn"],
        )
        self.store.save(record)
        with patch("atlas.autonomous_service.get_cycle_store", return_value=self.store):
            self.assertEqual(get_autonomous_cycle("cycle-1")["status"], "simulated")
            self.assertEqual(len(list_autonomous_cycles()), 1)

    def test_invalid_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_risk"):
            run_autonomous_cycle(max_risk=1.5)


if __name__ == "__main__":
    unittest.main()
