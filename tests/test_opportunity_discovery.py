import json
import tempfile
import unittest
from pathlib import Path

from atlas.opportunity_discovery import (
    AutonomousOpportunityDiscovery,
    OpportunitySignal,
    StaticOpportunitySource,
)


def signal(
    source_id: str,
    *,
    source_url: str | None = None,
    title: str = "Automated supplier intelligence",
    autonomy: float = 0.9,
    human_dependency: float = 0.1,
    risk: float = 0.2,
    expected_value: float = 0.8,
) -> OpportunitySignal:
    return OpportunitySignal(
        source_id=source_id,
        source_url=source_url or f"https://example.com/{source_id}",
        title=title,
        problem="Industrial SMEs lack verified supplier intelligence",
        target_customer="European industrial SME",
        proposed_offer="Evidence-backed automated supplier intelligence brief",
        expected_value=expected_value,
        autonomy=autonomy,
        learning_value=0.8,
        speed=0.8,
        human_dependency=human_dependency,
        cost=0.1,
        risk=risk,
    )


class OpportunityDiscoveryTests(unittest.TestCase):
    def test_discovers_ranks_and_writes_evidence_backed_opportunities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousOpportunityDiscovery().discover(
                sources=[
                    StaticOpportunitySource(
                        "market-feed",
                        [signal("strong"), signal("weaker", title="Technical document monitor", expected_value=0.5)],
                    )
                ],
                output_path=Path(tmpdir) / "discovery.json",
            )

            self.assertEqual(result.signal_count, 2)
            self.assertEqual(result.accepted_count, 2)
            self.assertGreaterEqual(
                result.opportunities[0].expected_value,
                result.opportunities[1].expected_value,
            )
            payload = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["accepted_count"], 2)
            self.assertTrue(payload["opportunities"][0]["evidence_references"])
            self.assertIn("decision_score", payload["opportunities"][0])

    def test_rejects_low_autonomy_high_dependency_and_high_risk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousOpportunityDiscovery().discover(
                sources=[
                    StaticOpportunitySource(
                        "feed",
                        [
                            signal("manual", autonomy=0.4),
                            signal("dependent", title="Manual negotiation service", human_dependency=0.8),
                            signal("risky", title="Unbounded speculative offer", risk=0.9),
                        ],
                    )
                ],
                output_path=Path(tmpdir) / "discovery.json",
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertEqual(result.rejected_count, 3)
            reasons = " ".join(item["reason"] for item in result.rejected)
            self.assertIn("autonomy below threshold", reasons)
            self.assertIn("human dependency above threshold", reasons)
            self.assertIn("risk above threshold", reasons)

    def test_deduplicates_same_offer_and_merges_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = signal("first", source_url="https://source-a.example/opportunity")
            second = signal("second", source_url="https://source-b.example/opportunity")
            result = AutonomousOpportunityDiscovery().discover(
                sources=[
                    StaticOpportunitySource("source-a", [first]),
                    StaticOpportunitySource("source-b", [second]),
                ],
                output_path=Path(tmpdir) / "discovery.json",
            )

            self.assertEqual(result.signal_count, 2)
            self.assertEqual(result.accepted_count, 1)
            self.assertEqual(
                result.opportunities[0].evidence_references,
                ["https://source-a.example/opportunity", "https://source-b.example/opportunity"],
            )

    def test_rejects_non_verifiable_source_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AutonomousOpportunityDiscovery().discover(
                sources=[StaticOpportunitySource("bad-feed", [signal("bad", source_url="invented-reference")])],
                output_path=Path(tmpdir) / "discovery.json",
            )

            self.assertEqual(result.accepted_count, 0)
            self.assertIn("absolute HTTP(S) URL", result.rejected[0]["reason"])


if __name__ == "__main__":
    unittest.main()
