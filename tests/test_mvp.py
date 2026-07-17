import json
import unittest
from atlas.runner import ROOT, _normalize_case_payload, run_all

class AtlasMVPTests(unittest.TestCase):
    def test_guarded_variant_is_promoted(self):
        summary = run_all()
        self.assertTrue(summary["promotion"]["promoted"])
        self.assertGreater(summary["guarded_v1"]["score"], summary["baseline"]["score"])
        self.assertEqual(summary["guarded_v1"]["critical_regressions"], 0)

    def test_evidence_written(self):
        run_all()
        lines = (ROOT / "results" / "evidence.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 12)
        self.assertIn("evaluation", json.loads(lines[0]))

    def test_legacy_case_id_is_normalized(self):
        payload = {
            "case_id": "legacy-001",
            "workflow": "email",
            "input": {},
            "expected": {},
        }
        normalized = _normalize_case_payload(payload)
        self.assertEqual(normalized["id"], "legacy-001")
        self.assertNotIn("case_id", normalized)

if __name__ == "__main__":
    unittest.main()
