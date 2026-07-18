from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.mission_evidence_pipeline import EvidenceItem, MissionEvidencePipeline, RawMission


def evidence(evidence_id: str, evidence_type: str, **overrides):
    values = {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "source": f"source://{evidence_id}",
        "claim": f"claim for {evidence_type}",
        "reliability": 0.85,
        "freshness": 0.90,
        "corroborated": True,
    }
    values.update(overrides)
    return EvidenceItem(**values)


class MissionEvidencePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = MissionEvidencePipeline()
        self.mission = RawMission("mission-1", "Find an autonomous B2B revenue opportunity")

    def test_ready_only_with_complete_reliable_evidence(self) -> None:
        items = [evidence(f"e-{kind}", kind) for kind in self.pipeline.REQUIRED_TYPES]
        result = self.pipeline.assess(self.mission, items)
        self.assertEqual(result.decision, "ready")
        self.assertFalse(result.missing_evidence_types)
        self.assertGreaterEqual(result.confidence, 0.65)

    def test_partial_evidence_generates_research_questions(self) -> None:
        result = self.pipeline.assess(self.mission, [
            evidence("e-demand", "demand"), evidence("e-price", "pricing")
        ])
        self.assertEqual(result.decision, "research_more")
        self.assertIn("competition", result.missing_evidence_types)
        self.assertTrue(result.research_questions)

    def test_weakly_evidenced_mission_is_rejected(self) -> None:
        result = self.pipeline.assess(self.mission, [evidence("e-demand", "demand")])
        self.assertEqual(result.decision, "reject")

    def test_stale_or_unreliable_evidence_is_rejected(self) -> None:
        result = self.pipeline.assess(self.mission, [
            evidence("e-demand", "demand", freshness=0.10),
            evidence("e-price", "pricing", reliability=0.20),
        ])
        self.assertEqual(result.accepted_evidence_ids, ())
        self.assertEqual(set(result.rejected_evidence_ids), {"e-demand", "e-price"})
        self.assertEqual(result.decision, "reject")

    def test_uncorroborated_evidence_reduces_confidence(self) -> None:
        strong = [evidence(f"s-{kind}", kind) for kind in self.pipeline.REQUIRED_TYPES]
        weak = [evidence(f"w-{kind}", kind, corroborated=False) for kind in self.pipeline.REQUIRED_TYPES]
        self.assertGreater(
            self.pipeline.assess(self.mission, strong).confidence,
            self.pipeline.assess(self.mission, weak).confidence,
        )

    def test_writes_versioned_artifact(self) -> None:
        result = self.pipeline.assess(self.mission, [evidence("e-demand", "demand")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mission_assessment.json"
            self.pipeline.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["assessment"]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
