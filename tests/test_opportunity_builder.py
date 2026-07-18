from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.opportunity_builder import (
    EvidenceBackedOpportunityBuilder,
    OpportunityDraft,
    ValidatedClaim,
)


def claim(claim_id: str, category: str, **overrides):
    values = {
        "claim_id": claim_id,
        "category": category,
        "statement": f"supported statement for {category}",
        "status": "supported",
        "confidence": 0.82,
        "source_ids": (f"source-{claim_id}", "independent-source"),
    }
    values.update(overrides)
    return ValidatedClaim(**values)


def draft(**overrides):
    values = {
        "opportunity_id": "opp-1",
        "title": "Automated B2B market brief",
        "target_customer": "industrial sourcing SMEs",
        "problem": "market research is slow and fragmented",
        "offer": "weekly evidence-backed prospect and market brief",
        "revenue_model": "monthly subscription",
        "expected_value": 0.75,
        "estimated_cost": 0.20,
        "risk": 0.25,
        "autonomy": 0.85,
        "success_metric": "qualified customer interviews",
        "success_threshold": 0.30,
        "experiment": "produce three briefs and request structured feedback",
        "claim_ids": tuple(f"c-{category}" for category in EvidenceBackedOpportunityBuilder.REQUIRED_CATEGORIES),
    }
    values.update(overrides)
    return OpportunityDraft(**values)


class OpportunityBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = EvidenceBackedOpportunityBuilder()
        self.claims = [claim(f"c-{category}", category) for category in self.builder.REQUIRED_CATEGORIES]

    def test_complete_supported_opportunity_is_ready(self):
        result = self.builder.build(draft(), self.claims)
        self.assertEqual(result.decision, "ready_for_experiment")
        self.assertIsNotNone(result.draft)
        self.assertFalse(result.blocking_claim_ids)

    def test_missing_category_requires_revision(self):
        result = self.builder.build(draft(), self.claims[:-1])
        self.assertEqual(result.decision, "revise")
        self.assertIn("missing supported categories", result.assumptions[0])
        self.assertIsNone(result.draft)

    def test_contested_claim_rejects_opportunity(self):
        claims = self.claims[:-1] + [claim("c-risk", "risk", status="contested")]
        result = self.builder.build(draft(), claims)
        self.assertEqual(result.decision, "reject")
        self.assertIn("c-risk", result.blocking_claim_ids)

    def test_weak_claim_and_bad_unit_economics_require_revision(self):
        claims = self.claims[:-1] + [claim("c-risk", "risk", confidence=0.30)]
        result = self.builder.build(draft(expected_value=0.20, estimated_cost=0.40), claims)
        self.assertEqual(result.decision, "revise")
        self.assertTrue(result.assumptions)

    def test_unreferenced_claims_do_not_inflate_confidence(self):
        extra = claim("extra", "demand", confidence=1.0)
        baseline = self.builder.build(draft(), self.claims)
        enriched = self.builder.build(draft(), self.claims + [extra])
        self.assertEqual(baseline.evidence_confidence, enriched.evidence_confidence)

    def test_writes_versioned_artifact(self):
        result = self.builder.build(draft(), self.claims)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opportunity.json"
            self.builder.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["result"]["decision"], "ready_for_experiment")


if __name__ == "__main__":
    unittest.main()
