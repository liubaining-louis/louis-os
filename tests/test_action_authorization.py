from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.action_authorization import ActionAuthorizationGate, ProposedAction


def action(**overrides):
    values = {
        "action_id": "act-1",
        "action_type": "write_local_artifact",
        "scope": "internal",
        "estimated_cost_score": 0.05,
        "human_dependency": 0.05,
        "reversible": True,
        "evidence_references": ("evidence://experiment/1",),
    }
    values.update(overrides)
    return ProposedAction(**values)


class ActionAuthorizationGateTests(unittest.TestCase):
    def test_auto_executes_bounded_reversible_internal_action(self) -> None:
        result = ActionAuthorizationGate().classify(action())
        self.assertEqual(result.decision, "auto_execute")

    def test_external_action_requires_approval(self) -> None:
        result = ActionAuthorizationGate().classify(action(scope="external"))
        self.assertEqual(result.decision, "requires_approval")
        self.assertIn("external side effect", result.reasons[0])

    def test_irreversible_action_requires_approval(self) -> None:
        result = ActionAuthorizationGate().classify(action(reversible=False))
        self.assertEqual(result.decision, "requires_approval")

    def test_forbidden_action_cannot_be_promoted(self) -> None:
        result = ActionAuthorizationGate().classify(action(action_type="payment", scope="external"))
        self.assertEqual(result.decision, "forbidden")

    def test_cost_and_dependency_limits_require_approval(self) -> None:
        result = ActionAuthorizationGate().classify(
            action(estimated_cost_score=0.50, human_dependency=0.40)
        )
        self.assertEqual(result.decision, "requires_approval")
        self.assertEqual(len(result.reasons), 2)

    def test_requires_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "evidence"):
            ActionAuthorizationGate().classify(action(evidence_references=()))

    def test_writes_versioned_artifact(self) -> None:
        gate = ActionAuthorizationGate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authorizations.json"
            gate.write([gate.classify(action())], path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["authorization_count"], 1)
        self.assertEqual(payload["authorizations"][0]["decision"], "auto_execute")


if __name__ == "__main__":
    unittest.main()
