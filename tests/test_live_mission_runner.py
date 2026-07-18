from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.live_mission_runner import (
    ControlledLiveMissionRunner,
    LiveSignal,
    MissionInput,
    ProspectCandidate,
)


class SignalAdapter:
    read_only = True

    def __init__(self, items):
        self.items = items

    def collect(self, mission, limit):
        return self.items


class ProspectSource:
    read_only = True

    def __init__(self, items):
        self.items = items

    def discover(self, mission, evidence, limit):
        return self.items


def mission() -> MissionInput:
    return MissionInput(
        mission_id="m1",
        objective="Validate industrial sourcing demand",
        offer="qualified industrial sourcing",
        target_segment="European industrial SMEs",
        consent_scope="commercial_research",
        maximum_web_signals=5,
        maximum_gmail_signals=5,
        maximum_prospects=5,
    )


def web(index: int) -> LiveSignal:
    return LiveSignal(f"w{index}", "web", f"evidence {index}", f"https://example.com/{index}")


class LiveMissionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = ControlledLiveMissionRunner(minimum_web_evidence=3)

    def test_requests_more_research_when_evidence_is_insufficient(self):
        result = self.runner.run(
            mission(),
            web_adapter=SignalAdapter([web(1)]),
            gmail_adapter=SignalAdapter([]),
            prospect_adapter=ProspectSource([]),
        )
        self.assertEqual(result.decision, "research_more")
        self.assertEqual(result.approval_actions, ())

    def test_blocks_when_no_prospect_is_qualified(self):
        result = self.runner.run(
            mission(),
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([]),
            prospect_adapter=ProspectSource([
                ProspectCandidate("p1", "Low Fit Ltd", 0.3, ("w1",)),
                ProspectCandidate("p2", "Unknown Evidence Ltd", 0.9, ("missing",)),
            ]),
        )
        self.assertEqual(result.decision, "blocked")
        self.assertEqual(result.qualified_prospects, 0)

    def test_creates_only_approval_required_outreach(self):
        result = self.runner.run(
            mission(),
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([]),
            prospect_adapter=ProspectSource([
                ProspectCandidate("p1", "Industrial Buyer", 0.9, ("w1", "w2")),
            ]),
        )
        self.assertEqual(result.decision, "ready_for_approval")
        self.assertEqual(result.qualified_prospects, 1)
        self.assertTrue(all(item.authorization == "requires_approval" for item in result.approval_actions))

    def test_enters_learning_state_when_real_gmail_signal_exists(self):
        result = self.runner.run(
            mission(),
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([
                LiveSignal("g1", "gmail", "Interested, please quote", "gmail://thread/1")
            ]),
            prospect_adapter=ProspectSource([
                ProspectCandidate("p1", "Industrial Buyer", 0.9, ("w1",)),
            ]),
        )
        self.assertEqual(result.decision, "learning")
        self.assertEqual(result.accepted_gmail_signals, 1)

    def test_rejects_non_read_only_adapters(self):
        adapter = SignalAdapter([web(1), web(2), web(3)])
        adapter.read_only = False
        with self.assertRaises(ValueError):
            self.runner.run(
                mission(),
                web_adapter=adapter,
                gmail_adapter=SignalAdapter([]),
                prospect_adapter=ProspectSource([]),
            )

    def test_writes_auditable_artifact(self):
        result = self.runner.run(
            mission(),
            web_adapter=SignalAdapter([web(1), web(2), web(3)]),
            gmail_adapter=SignalAdapter([]),
            prospect_adapter=ProspectSource([
                ProspectCandidate("p1", "Industrial Buyer", 0.9, ("w1",)),
            ]),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live_mission.json"
            self.runner.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["live_mission"]["decision"], "ready_for_approval")


if __name__ == "__main__":
    unittest.main()
