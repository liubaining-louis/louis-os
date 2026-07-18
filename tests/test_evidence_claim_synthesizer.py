from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.evidence_claim_synthesizer import ClaimEvidence, EvidenceClaimSynthesizer


def item(source_id: str, stance: str = "support", **overrides):
    values = {
        "claim_key": "market-demand",
        "statement": "Industrial buyers show recurring demand.",
        "source_id": source_id,
        "source_uri": f"https://source.example/{source_id}",
        "stance": stance,
        "reliability": 0.9,
        "freshness": 0.9,
    }
    values.update(overrides)
    return ClaimEvidence(**values)


class EvidenceClaimSynthesizerTests(unittest.TestCase):
    def test_supports_claim_with_two_independent_strong_sources(self):
        result = EvidenceClaimSynthesizer().synthesize([item("s1"), item("s2")])[0]
        self.assertEqual(result.decision, "supported")
        self.assertGreaterEqual(result.confidence, 0.6)

    def test_blocks_single_source_claim(self):
        result = EvidenceClaimSynthesizer().synthesize([item("s1")])[0]
        self.assertEqual(result.decision, "insufficient")

    def test_detects_material_contradiction(self):
        result = EvidenceClaimSynthesizer().synthesize([
            item("s1"), item("s2"),
            item("o1", "oppose"), item("o2", "oppose"),
        ])[0]
        self.assertEqual(result.decision, "contested")
        self.assertTrue(result.opposing_source_ids)

    def test_strong_support_can_outweigh_weak_opposition(self):
        result = EvidenceClaimSynthesizer().synthesize([
            item("s1"), item("s2"), item("s3"),
            item("o1", "oppose", reliability=0.2, freshness=0.3),
        ])[0]
        self.assertEqual(result.decision, "supported")

    def test_deterministic_claim_ordering(self):
        a = item("a1")
        b = item("b1", claim_key="pricing", statement="Price is viable.")
        results = EvidenceClaimSynthesizer(minimum_independent_sources=1).synthesize([b, a])
        self.assertEqual([result.claim_key for result in results], ["market-demand", "pricing"])

    def test_writes_versioned_artifact(self):
        claims = EvidenceClaimSynthesizer().synthesize([item("s1"), item("s2")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            EvidenceClaimSynthesizer().write(claims, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["supported_count"], 1)


if __name__ == "__main__":
    unittest.main()
