import json
import tempfile
import unittest
from pathlib import Path

from atlas.monetization_dashboard import build_snapshot


class MonetizationDashboardTest(unittest.TestCase):
    def test_empty_snapshot_never_invents_results(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = build_snapshot(Path(directory))
        self.assertEqual(snapshot["metrics"]["revenue_received"], 0)
        self.assertEqual(snapshot["integrity"]["experiment_count"], 0)
        self.assertTrue(snapshot["integrity"]["data_is_empty"])

    def test_snapshot_computes_verified_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results").mkdir()
            (root / "results" / "monetization.json").write_text(json.dumps({
                "revenue_received": 120,
                "weighted_pipeline": 300,
                "hours_invested": 4,
                "outreach_sent": 10,
                "qualified_replies": 2,
                "conversions": 1,
            }), encoding="utf-8")
            (root / "results" / "monetization_experiments.jsonl").write_text(json.dumps({
                "timestamp": "2026-07-19T00:00:00Z",
                "title": "Research microservice",
                "domain": "freelancing",
                "stage": "delivery",
                "probability": 0.8,
                "decision": "continue",
                "proof": "invoice-001",
            }) + "\n", encoding="utf-8")
            snapshot = build_snapshot(root)
        self.assertEqual(snapshot["metrics"]["revenue_per_hour"], 30)
        self.assertEqual(snapshot["metrics"]["reply_rate"], 0.2)
        self.assertEqual(snapshot["metrics"]["conversion_rate"], 0.1)
        self.assertEqual(snapshot["mission"], "Research microservice")
        self.assertFalse(snapshot["integrity"]["data_is_empty"])


if __name__ == "__main__":
    unittest.main()
