from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.opportunity_discovery import OpportunitySignal
from atlas.opportunity_novelty import OpportunityNoveltyLedger


def signal(source_id: str, title: str = "New market need") -> OpportunitySignal:
    return OpportunitySignal(
        source_id=source_id,
        source_url="https://example.com/opportunity",
        title=title,
        problem="Manual supplier qualification is slow",
        target_customer="European industrial buyer",
        proposed_offer="Automated supplier qualification service",
        expected_value=0.8,
        autonomy=0.9,
        learning_value=0.8,
        speed=0.7,
        human_dependency=0.1,
        cost=0.2,
        risk=0.2,
        observed_at="2026-07-18T00:00:00Z",
    )


class OpportunityNoveltyLedgerTests(unittest.TestCase):
    def test_filters_duplicates_within_one_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = OpportunityNoveltyLedger(Path(tmpdir) / "ledger.json")
            novel, decisions = ledger.filter_novel([signal("a"), signal("b")])

        self.assertEqual([item.source_id for item in novel], ["a"])
        self.assertTrue(decisions[0].is_novel)
        self.assertFalse(decisions[1].is_novel)

    def test_persists_seen_fingerprints_across_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.json"
            first = OpportunityNoveltyLedger(path)
            first.filter_novel([signal("first")])

            second = OpportunityNoveltyLedger(path)
            novel, decisions = second.filter_novel([signal("second")])

            self.assertEqual(novel, [])
            self.assertFalse(decisions[0].is_novel)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(len(payload["fingerprints"]), 1)

    def test_changed_business_content_is_novel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = OpportunityNoveltyLedger(Path(tmpdir) / "ledger.json")
            novel, _ = ledger.filter_novel([signal("a"), signal("b", title="Different need")])

        self.assertEqual(len(novel), 2)

    def test_rejects_unknown_ledger_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.json"
            path.write_text(json.dumps({"schema_version": "2.0", "fingerprints": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                OpportunityNoveltyLedger(path)


if __name__ == "__main__":
    unittest.main()
